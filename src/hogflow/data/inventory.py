"""Local-only Phase 3 video inventory workflow and command-line entrypoint."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from collections import Counter
from dataclasses import asdict, replace
from io import StringIO
from pathlib import Path
from typing import Any, Sequence

from hogflow.core import HogFlowError, InputDataError, configure_logging, get_logger
from hogflow.data.models import (
    DatasetInventory,
    DatasetInventorySummary,
    ManualReviewMetadata,
    SuitabilityLabel,
    SuitabilitySettings,
    VideoFileMetadata,
    VideoInspectionSettings,
)
from hogflow.data.validation import (
    classify_suitability,
    discover_video_files,
    load_clip_manifest,
    load_review_sidecar,
    review_sidecar_path,
)
from hogflow.video.metadata import OpenCVVideoMetadataReader

LOGGER = get_logger(__name__)
_LEGAL_REMINDER = (
    "A file must not be used merely because it is publicly viewable. Confirm and record "
    "project authorization or a legally usable license before detection, tracking, or counting work."
)


def create_inventory(
    input_root: str | Path,
    *,
    inspection_settings: VideoInspectionSettings | None = None,
    suitability_settings: SuitabilitySettings | None = None,
    clip_manifest_path: str | Path | None = None,
    metadata_reader: OpenCVVideoMetadataReader | None = None,
) -> DatasetInventory:
    """Inspect supported local clips and return an immutable inventory.

    The function reads but never modifies source clips. Adjacent ``.review.json``
    files provide explicit authorization and human scene confirmations.
    """

    root = Path(input_root)
    relative_paths = discover_video_files(root)
    reader = metadata_reader or OpenCVVideoMetadataReader(inspection_settings)
    suitability = suitability_settings or SuitabilitySettings()
    files: list[VideoFileMetadata] = []

    for relative_path in relative_paths:
        video_path = root / relative_path
        metadata = reader.inspect(video_path, relative_path=relative_path)
        review, review_errors = _read_optional_review(video_path)
        errors = list(metadata.validation_errors)
        errors.extend(review_errors)
        if review is None or not review.authorized_for_project:
            errors.append("authorization_not_confirmed")
        metadata = replace(
            metadata,
            validation_errors=tuple(dict.fromkeys(errors)),
            review_metadata=review,
        )
        metadata = replace(
            metadata,
            suitability_labels=classify_suitability(metadata, review, suitability),
        )
        files.append(metadata)

    manifest = load_clip_manifest(clip_manifest_path) if clip_manifest_path else ()
    return DatasetInventory(
        files=tuple(files),
        summary=_summarize(files),
        clip_manifest=manifest,
    )


def write_inventory_outputs(inventory: DatasetInventory, output_directory: str | Path) -> None:
    """Atomically write deterministic JSON, CSV, and Markdown inventory reports."""

    output = Path(output_directory)
    try:
        output.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InputDataError(f"Unable to create inventory output directory: {output}") from exc
    if not output.is_dir():
        raise InputDataError(f"Inventory output path is not a directory: {output}")

    payload = {
        "format_version": 1,
        "summary": _to_json_value(inventory.summary),
        "files": [_to_json_value(item) for item in inventory.files],
        "clip_manifest": [_to_json_value(item) for item in inventory.clip_manifest],
    }
    _atomic_write_text(
        output / "inventory.json",
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    _atomic_write_text(output / "inventory.csv", _render_csv(inventory.files))
    _atomic_write_text(output / "inventory.md", _render_markdown(inventory))


def build_parser() -> argparse.ArgumentParser:
    """Create the Phase 3 local inventory command-line parser."""

    parser = argparse.ArgumentParser(
        description="Inventory authorized or legally usable local video clips without modifying them."
    )
    parser.add_argument("--input", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/inventory"))
    parser.add_argument("--clip-manifest", type=Path)
    parser.add_argument("--sample-frames", type=int, default=12)
    parser.add_argument("--static-threshold-percent", type=float, default=0.10)
    parser.add_argument("--moving-threshold-percent", type=float, default=0.75)
    parser.add_argument("--minimum-motion-features", type=int, default=8)
    parser.add_argument("--minimum-motion-pairs", type=int, default=2)
    parser.add_argument("--max-sample-dimension", type=int, default=640)
    parser.add_argument("--minimum-detection-duration", type=float, default=2.0)
    parser.add_argument("--minimum-tracking-duration", type=float, default=5.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run local inventory generation and return a process status code."""

    configure_logging()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        inventory = create_inventory(
            args.input,
            inspection_settings=VideoInspectionSettings(
                sample_frame_count=args.sample_frames,
                static_threshold_percent=args.static_threshold_percent,
                moving_threshold_percent=args.moving_threshold_percent,
                minimum_motion_features=args.minimum_motion_features,
                minimum_motion_pairs=args.minimum_motion_pairs,
                max_sample_dimension=args.max_sample_dimension,
            ),
            suitability_settings=SuitabilitySettings(
                minimum_detection_duration_seconds=args.minimum_detection_duration,
                minimum_tracking_duration_seconds=args.minimum_tracking_duration,
            ),
            clip_manifest_path=args.clip_manifest,
        )
        write_inventory_outputs(inventory, args.output)
    except HogFlowError as exc:
        parser.error(str(exc))

    summary = inventory.summary
    LOGGER.info(
        "Inventory complete: %d files (%d readable, %d unreadable)",
        summary.total_files,
        summary.readable_files,
        summary.unreadable_files,
    )
    return 0


def _read_optional_review(video_path: Path) -> tuple[ManualReviewMetadata | None, tuple[str, ...]]:
    sidecar = review_sidecar_path(video_path)
    if not sidecar.exists():
        return None, ()
    try:
        return load_review_sidecar(sidecar), ()
    except InputDataError as exc:
        LOGGER.warning("Ignoring invalid review sidecar for %s: %s", video_path.name, exc)
        return None, ("invalid_review_sidecar",)


def _summarize(files: list[VideoFileMetadata]) -> DatasetInventorySummary:
    resolutions = Counter(
        f"{item.width}x{item.height}"
        if item.width is not None and item.height is not None
        else "unknown"
        for item in files
    )
    stability = Counter(item.stability_label.value for item in files)
    suitability = Counter(label.value for item in files for label in item.suitability_labels)
    fps_values = [item.fps for item in files if item.fps is not None]
    readable = sum(item.readable for item in files)
    return DatasetInventorySummary(
        total_files=len(files),
        readable_files=readable,
        unreadable_files=len(files) - readable,
        total_duration_seconds=sum(item.duration_seconds or 0.0 for item in files),
        total_size_bytes=sum(item.file_size_bytes for item in files),
        resolution_distribution=tuple(sorted(resolutions.items())),
        stability_counts=tuple(sorted(stability.items())),
        suitability_counts=tuple(sorted(suitability.items())),
        fps_min=min(fps_values) if fps_values else None,
        fps_max=max(fps_values) if fps_values else None,
    )


def _to_json_value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: _to_json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _to_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_to_json_value(item) for item in value]
    return value


def _render_csv(files: tuple[VideoFileMetadata, ...]) -> str:
    stream = StringIO(newline="")
    fieldnames = (
        "relative_path",
        "file_size_bytes",
        "container_extension",
        "duration_seconds",
        "fps",
        "frame_count",
        "width",
        "height",
        "codec",
        "readable",
        "sampled_frame_count",
        "stability_score_percent",
        "stability_label",
        "suitability_labels",
        "validation_errors",
        "authorized_for_project",
    )
    writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for item in files:
        writer.writerow(
            {
                "relative_path": item.relative_path,
                "file_size_bytes": item.file_size_bytes,
                "container_extension": item.container_extension,
                "duration_seconds": item.duration_seconds,
                "fps": item.fps,
                "frame_count": item.frame_count,
                "width": item.width,
                "height": item.height,
                "codec": item.codec,
                "readable": item.readable,
                "sampled_frame_count": item.sampled_frame_count,
                "stability_score_percent": item.stability_score_percent,
                "stability_label": item.stability_label.value,
                "suitability_labels": ";".join(label.value for label in item.suitability_labels),
                "validation_errors": ";".join(item.validation_errors),
                "authorized_for_project": (
                    item.review_metadata.authorized_for_project
                    if item.review_metadata is not None
                    else False
                ),
            }
        )
    return stream.getvalue()


def _render_markdown(inventory: DatasetInventory) -> str:
    summary = inventory.summary
    duration_minutes = summary.total_duration_seconds / 60.0
    lines = [
        "# HogFlow Local Video Inventory",
        "",
        "> This report is an inventory aid, not technical, legal, or commercial validation.",
        "",
        "## Summary",
        "",
        f"- Clips: {summary.total_files}",
        f"- Readable / unreadable: {summary.readable_files} / {summary.unreadable_files}",
        f"- Total duration: {summary.total_duration_seconds:.2f} seconds "
        f"({duration_minutes:.2f} minutes)",
        f"- Total size: {summary.total_size_bytes} bytes",
        f"- FPS range: {_format_range(summary.fps_min, summary.fps_max)}",
        "",
        "## Resolution distribution",
        "",
        *_count_lines(summary.resolution_distribution),
        "",
        "## Automatic camera-stability labels",
        "",
        *_count_lines(summary.stability_counts),
        "",
        "Automatic stability uses bounded feature-based global-motion estimates. It can be "
        "wrong when animals or other foreground objects dominate sampled features.",
        "",
        "## Inventory suitability labels",
        "",
        *_count_lines(summary.suitability_counts),
        "",
        "Counting candidacy is never granted from automatic metadata alone. It requires an "
        "authorized sidecar with manual scene confirmations.",
        "",
        "## Validation problems",
        "",
    ]
    problems = [item for item in inventory.files if item.validation_errors]
    if problems:
        lines.extend(("| File | Problems |", "| --- | --- |"))
        lines.extend(
            f"| `{_escape_table(item.relative_path)}` | "
            f"{_escape_table(', '.join(item.validation_errors))} |"
            for item in problems
        )
    else:
        lines.append("None recorded.")

    lines.extend(("", "## Files requiring manual review", ""))
    manual_review = [
        item
        for item in inventory.files
        if SuitabilityLabel.NEEDS_MANUAL_REVIEW in item.suitability_labels
    ]
    if manual_review:
        lines.extend(f"- `{item.relative_path}`" for item in manual_review)
    else:
        lines.append("None.")

    lines.extend(
        (
            "",
            "## Authorization reminder",
            "",
            _LEGAL_REMINDER,
            "",
        )
    )
    return "\n".join(lines)


def _count_lines(entries: tuple[tuple[str, int], ...]) -> list[str]:
    return [f"- {label}: {count}" for label, count in entries] or ["- None"]


def _format_range(minimum: float | None, maximum: float | None) -> str:
    if minimum is None or maximum is None:
        return "not available"
    return f"{minimum:.3f}–{maximum:.3f}"


def _escape_table(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _atomic_write_text(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise InputDataError(f"Unable to write inventory output: {path.name}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
