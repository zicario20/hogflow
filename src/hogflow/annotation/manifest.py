"""Sanitized annotation-manifest construction and deterministic serialization."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

from hogflow.annotation.models import (
    ANNOTATION_POLICY_VERSION,
    PIG_CLASS_ID,
    PIG_CLASS_NAME,
    AnnotationDatasetManifest,
    AnnotationFrameRecord,
    AnnotationStatus,
    DatasetSplit,
    ManifestValidationStatus,
)
from hogflow.core import HogFlowError, InputDataError, configure_logging, get_logger

LOGGER = get_logger(__name__)


def build_annotation_manifest(
    extraction_report: Mapping[str, Any],
    status_map: Mapping[str, Any],
) -> AnnotationDatasetManifest:
    """Build one path-private manifest from sanitized extraction and status data."""

    records_payload = extraction_report.get("records")
    status_payload = status_map.get("frames")
    if not isinstance(records_payload, list):
        raise InputDataError("Extraction report must contain a records array.")
    if not isinstance(status_payload, dict):
        raise InputDataError("Annotation status map must contain a frames object.")
    dataset_id = status_map.get("dataset_id")
    frame_records: list[AnnotationFrameRecord] = []
    extraction_ids: set[str] = set()
    for item in records_payload:
        if not isinstance(item, dict):
            raise InputDataError("Extraction report records must be JSON objects.")
        frame_id = item.get("frame_id")
        if not isinstance(frame_id, str):
            raise InputDataError("Extraction report contains an invalid opaque frame ID.")
        if frame_id in extraction_ids:
            raise InputDataError("Extraction report contains duplicate frame IDs.")
        extraction_ids.add(frame_id)
        frame_status = status_payload.get(frame_id)
        if not isinstance(frame_status, dict):
            raise InputDataError(f"Annotation status is missing for opaque frame {frame_id!r}.")
        try:
            frame_records.append(
                AnnotationFrameRecord(
                    frame_id=frame_id,
                    clip_id=item["clip_id"],
                    split=DatasetSplit(item["split"]),
                    image_relative_path=item["image_relative_path"],
                    width=item["width"],
                    height=item["height"],
                    annotation_status=AnnotationStatus(frame_status["status"]),
                    bounding_box_count=frame_status.get("bounding_box_count", 0),
                    checksum_sha256=item["checksum_sha256"],
                    validation_status=ManifestValidationStatus.PENDING,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InputDataError(
                f"Manifest input is invalid for opaque frame {frame_id!r}."
            ) from exc
    unexpected_statuses = sorted(set(status_payload) - extraction_ids)
    if unexpected_statuses:
        raise InputDataError(
            "Annotation status map contains unknown opaque frame IDs: "
            + ", ".join(unexpected_statuses)
        )
    _enforce_source_split_isolation(frame_records)
    return AnnotationDatasetManifest(
        schema_version=1,
        dataset_id=dataset_id,
        annotation_policy_version=ANNOTATION_POLICY_VERSION,
        class_map=((PIG_CLASS_ID, PIG_CLASS_NAME),),
        frames=tuple(sorted(frame_records, key=lambda frame: frame.frame_id)),
    )


def manifest_to_dict(manifest: AnnotationDatasetManifest) -> dict[str, Any]:
    """Return a stable JSON-compatible representation of a manifest."""

    if not isinstance(manifest, AnnotationDatasetManifest):
        raise InputDataError("manifest must be AnnotationDatasetManifest.")
    return {
        "annotation_policy_version": manifest.annotation_policy_version,
        "class_map": [
            {"class_id": class_id, "class_name": class_name}
            for class_id, class_name in manifest.class_map
        ],
        "dataset_id": manifest.dataset_id,
        "frames": [
            {
                "annotation_status": frame.annotation_status.value,
                "bounding_box_count": frame.bounding_box_count,
                "checksum_sha256": frame.checksum_sha256,
                "clip_id": frame.clip_id,
                "frame_id": frame.frame_id,
                "height": frame.height,
                "image_relative_path": frame.image_relative_path,
                "split": frame.split.value,
                "validation_status": frame.validation_status.value,
                "width": frame.width,
            }
            for frame in manifest.frames
        ],
        "schema_version": manifest.schema_version,
    }


def write_annotation_manifest(
    manifest: AnnotationDatasetManifest,
    path: str | Path,
) -> None:
    """Atomically write a deterministic sanitized local manifest."""

    _atomic_write_json(
        Path(path),
        manifest_to_dict(manifest),
        description="annotation dataset manifest",
    )


def load_annotation_manifest(path: str | Path) -> AnnotationDatasetManifest:
    """Load a sanitized annotation manifest without accepting source paths."""

    payload = _load_json_object(path, description="annotation dataset manifest")
    try:
        class_payload = payload["class_map"]
        frame_payload = payload["frames"]
        if not isinstance(class_payload, list) or not isinstance(frame_payload, list):
            raise TypeError
        class_map = tuple((item["class_id"], item["class_name"]) for item in class_payload)
        frames = tuple(
            AnnotationFrameRecord(
                frame_id=item["frame_id"],
                clip_id=item["clip_id"],
                split=DatasetSplit(item["split"]),
                image_relative_path=item["image_relative_path"],
                width=item["width"],
                height=item["height"],
                annotation_status=AnnotationStatus(item["annotation_status"]),
                bounding_box_count=item["bounding_box_count"],
                checksum_sha256=item["checksum_sha256"],
                validation_status=ManifestValidationStatus(item["validation_status"]),
            )
            for item in frame_payload
        )
        return AnnotationDatasetManifest(
            schema_version=payload["schema_version"],
            dataset_id=payload["dataset_id"],
            annotation_policy_version=payload["annotation_policy_version"],
            class_map=class_map,
            frames=frames,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise InputDataError("Annotation dataset manifest has an invalid structure.") from exc


def prepare_manifest(
    *,
    extraction_report_path: str | Path,
    status_map_path: str | Path,
    output_path: str | Path,
) -> AnnotationDatasetManifest:
    """Load local sanitized inputs, build a manifest, and write it."""

    manifest = build_annotation_manifest(
        _load_json_object(extraction_report_path, description="extraction report"),
        _load_json_object(status_map_path, description="annotation status map"),
    )
    write_annotation_manifest(manifest, output_path)
    return manifest


def build_parser() -> argparse.ArgumentParser:
    """Create the sanitized annotation-manifest CLI parser."""

    parser = argparse.ArgumentParser(
        description="Build a sanitized local annotation dataset manifest."
    )
    parser.add_argument("--extraction-report", type=Path, required=True)
    parser.add_argument("--status-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Build one local manifest and return a process status code."""

    configure_logging()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        manifest = prepare_manifest(
            extraction_report_path=arguments.extraction_report,
            status_map_path=arguments.status_map,
            output_path=arguments.output,
        )
    except HogFlowError as exc:
        parser.error(str(exc))
    LOGGER.info("Annotation manifest complete: %d opaque frames", len(manifest.frames))
    return 0


def _enforce_source_split_isolation(frames: Sequence[AnnotationFrameRecord]) -> None:
    split_by_clip: dict[str, DatasetSplit] = {}
    for frame in frames:
        previous = split_by_clip.setdefault(frame.clip_id, frame.split)
        if previous is not frame.split:
            raise InputDataError(
                f"Opaque source clip {frame.clip_id!r} appears in more than one dataset split."
            )


def _load_json_object(path: str | Path, *, description: str) -> dict[str, Any]:
    input_path = Path(path)
    if not input_path.is_file():
        raise InputDataError(f"The local {description} is missing or is not a file.")
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputDataError(f"The local {description} is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise InputDataError(f"The local {description} must contain one JSON object.")
    return payload


def _atomic_write_json(path: Path, payload: Mapping[str, Any], *, description: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
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
        raise InputDataError(f"Unable to write the sanitized {description}.") from exc


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "build_annotation_manifest",
    "load_annotation_manifest",
    "manifest_to_dict",
    "prepare_manifest",
    "write_annotation_manifest",
]
