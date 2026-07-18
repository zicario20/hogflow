"""Local OpenCV frame extraction behind the Phase 4.2 infrastructure boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from hogflow.annotation.models import (
    DatasetSplit,
    validate_phase4_identifier,
    validate_relative_workspace_path,
)
from hogflow.core import (
    DependencyUnavailableError,
    HogFlowError,
    InputDataError,
    configure_logging,
    get_logger,
)
from hogflow.data.frame_selection import FrameSelectionPlan, PlannedFrame, read_frame_selection_plan

LOGGER = get_logger(__name__)


class ImageFormat(str, Enum):
    """Supported explicit frame-output encodings."""

    JPEG = "jpg"
    PNG = "png"


class ExtractedFrameStatus(str, Enum):
    """Outcome for one successfully resolved local frame."""

    EXTRACTED = "extracted"
    EXISTING_VERIFIED = "existing_verified"


@dataclass(frozen=True, slots=True)
class ExtractedFrameRecord:
    """Sanitized extraction result containing no source filename or path."""

    frame_id: str
    clip_id: str
    split: DatasetSplit
    image_relative_path: str
    planned_timestamp_seconds: float
    actual_timestamp_seconds: float | None
    width: int
    height: int
    checksum_sha256: str
    status: ExtractedFrameStatus

    def __post_init__(self) -> None:
        validate_phase4_identifier(self.frame_id, field_name="frame_id")
        validate_phase4_identifier(self.clip_id, field_name="clip_id")
        if not isinstance(self.split, DatasetSplit):
            raise InputDataError("split must be a DatasetSplit value.")
        validate_relative_workspace_path(
            self.image_relative_path,
            field_name="image_relative_path",
        )
        if not self.image_relative_path.startswith(f"images/{self.split.value}/{self.frame_id}."):
            raise InputDataError("Extracted image path must use opaque IDs and its assigned split.")
        if (
            not isinstance(self.planned_timestamp_seconds, (int, float))
            or isinstance(self.planned_timestamp_seconds, bool)
            or not math.isfinite(self.planned_timestamp_seconds)
            or self.planned_timestamp_seconds < 0
        ):
            raise InputDataError("planned_timestamp_seconds must be non-negative.")
        if self.actual_timestamp_seconds is not None and (
            not isinstance(self.actual_timestamp_seconds, (int, float))
            or isinstance(self.actual_timestamp_seconds, bool)
            or not math.isfinite(self.actual_timestamp_seconds)
            or self.actual_timestamp_seconds < 0
        ):
            raise InputDataError("actual_timestamp_seconds must be non-negative when present.")
        if (
            not isinstance(self.width, int)
            or isinstance(self.width, bool)
            or self.width <= 0
            or not isinstance(self.height, int)
            or isinstance(self.height, bool)
            or self.height <= 0
        ):
            raise InputDataError("Extracted image dimensions must be positive.")
        if (
            not isinstance(self.checksum_sha256, str)
            or len(self.checksum_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.checksum_sha256)
        ):
            raise InputDataError("checksum_sha256 must be lowercase SHA-256 text.")
        if not isinstance(self.status, ExtractedFrameStatus):
            raise InputDataError("status must be ExtractedFrameStatus.")


@dataclass(frozen=True, slots=True)
class FrameExtractionReport:
    """Deterministic sanitized extraction report."""

    image_format: ImageFormat
    records: tuple[ExtractedFrameRecord, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.image_format, ImageFormat):
            raise InputDataError("image_format must be ImageFormat.")
        if not isinstance(self.records, tuple) or not all(
            isinstance(record, ExtractedFrameRecord) for record in self.records
        ):
            raise InputDataError("records must be an immutable ExtractedFrameRecord tuple.")
        frame_ids = tuple(record.frame_id for record in self.records)
        if tuple(sorted(frame_ids)) != frame_ids or len(set(frame_ids)) != len(frame_ids):
            raise InputDataError("Extraction records must have unique frame IDs in sorted order.")


def load_local_source_map(path: str | Path) -> dict[str, Path]:
    """Load the ignored clip-to-path map without logging or returning path text."""

    payload = _load_json_object(path, description="local source map")
    if payload.get("format_version") != 1 or not isinstance(payload.get("sources"), dict):
        raise InputDataError("Local source map must use format_version 1 and a sources object.")
    sources: dict[str, Path] = {}
    for clip_id, raw_path in payload["sources"].items():
        validate_phase4_identifier(clip_id, field_name="clip_id")
        if not isinstance(raw_path, str) or not raw_path:
            raise InputDataError(f"Local source for clip {clip_id!r} must be a non-empty path.")
        sources[clip_id] = Path(raw_path)
    return sources


def extract_frames(
    plan: FrameSelectionPlan,
    source_map: Mapping[str, Path],
    output_root: str | Path,
    *,
    image_format: ImageFormat = ImageFormat.JPEG,
) -> FrameExtractionReport:
    """Extract planned frames locally with idempotent content verification."""

    if not isinstance(plan, FrameSelectionPlan):
        raise InputDataError("plan must be FrameSelectionPlan.")
    if not isinstance(image_format, ImageFormat):
        raise InputDataError("image_format must be ImageFormat.")
    root = Path(output_root)
    _prepare_output_structure(root)
    needed_clip_ids = {frame.clip_id for frame in plan.frames}
    if not needed_clip_ids.issubset(source_map):
        missing = sorted(needed_clip_ids - set(source_map))
        raise InputDataError("Local source map is missing opaque clip IDs: " + ", ".join(missing))

    records: list[ExtractedFrameRecord] = []
    frames_by_clip: dict[str, list[PlannedFrame]] = {}
    for frame in plan.frames:
        frames_by_clip.setdefault(frame.clip_id, []).append(frame)
    for clip_id in sorted(frames_by_clip):
        source_path = Path(source_map[clip_id])
        if not source_path.is_file():
            raise InputDataError(f"Local source for opaque clip {clip_id!r} is unavailable.")
        records.extend(
            _extract_clip_frames(
                source_path,
                frames_by_clip[clip_id],
                root,
                image_format=image_format,
            )
        )
    return FrameExtractionReport(
        image_format=image_format,
        records=tuple(sorted(records, key=lambda record: record.frame_id)),
    )


def write_extraction_report(report: FrameExtractionReport, path: str | Path) -> None:
    """Write a sanitized local extraction report atomically."""

    if not isinstance(report, FrameExtractionReport):
        raise InputDataError("report must be FrameExtractionReport.")
    payload = {
        "format_version": 1,
        "image_format": report.image_format.value,
        "summary": {
            "extracted": sum(
                record.status is ExtractedFrameStatus.EXTRACTED for record in report.records
            ),
            "existing_verified": sum(
                record.status is ExtractedFrameStatus.EXISTING_VERIFIED for record in report.records
            ),
            "total": len(report.records),
        },
        "records": [
            {
                "actual_timestamp_seconds": record.actual_timestamp_seconds,
                "checksum_sha256": record.checksum_sha256,
                "clip_id": record.clip_id,
                "frame_id": record.frame_id,
                "height": record.height,
                "image_relative_path": record.image_relative_path,
                "planned_timestamp_seconds": record.planned_timestamp_seconds,
                "split": record.split.value,
                "status": record.status.value,
                "width": record.width,
            }
            for record in report.records
        ],
    }
    _atomic_write_json(Path(path), payload, description="extraction report")


def run_extraction(
    *,
    plan_path: str | Path,
    source_map_path: str | Path,
    output_root: str | Path,
    image_format: ImageFormat,
    report_path: str | Path | None = None,
) -> FrameExtractionReport:
    """Load local inputs, extract frames, and write the sanitized report."""

    plan = read_frame_selection_plan(plan_path)
    report = extract_frames(
        plan,
        load_local_source_map(source_map_path),
        output_root,
        image_format=image_format,
    )
    destination = (
        Path(report_path)
        if report_path is not None
        else Path(output_root) / "metadata" / "extraction_report.json"
    )
    write_extraction_report(report, destination)
    return report


def build_parser() -> argparse.ArgumentParser:
    """Create the local frame-extraction CLI parser."""

    parser = argparse.ArgumentParser(
        description="Extract opaque planned frames from authorized local videos."
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--source-map", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=("jpg", "png"), default="jpg")
    parser.add_argument("--report", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run local extraction and return a process status code."""

    configure_logging()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        report = run_extraction(
            plan_path=arguments.plan,
            source_map_path=arguments.source_map,
            output_root=arguments.output,
            image_format=ImageFormat(arguments.format),
            report_path=arguments.report,
        )
    except HogFlowError as exc:
        parser.error(str(exc))
    LOGGER.info("Frame extraction complete: %d opaque frames", len(report.records))
    return 0


def _extract_clip_frames(
    source_path: Path,
    frames: Sequence[PlannedFrame],
    output_root: Path,
    *,
    image_format: ImageFormat,
) -> list[ExtractedFrameRecord]:
    cv2 = _require_cv2()
    capture = cv2.VideoCapture(str(source_path))
    if not capture.isOpened():
        capture.release()
        clip_id = frames[0].clip_id
        raise InputDataError(f"Local video for opaque clip {clip_id!r} cannot be opened.")
    records: list[ExtractedFrameRecord] = []
    extension = f".{image_format.value}"
    try:
        for planned in sorted(frames, key=lambda frame: frame.planned_timestamp_seconds):
            capture.set(cv2.CAP_PROP_POS_MSEC, planned.planned_timestamp_seconds * 1000.0)
            ok, image = capture.read()
            if not ok or image is None or getattr(image, "size", 0) == 0:
                raise InputDataError(f"Unable to decode planned opaque frame {planned.frame_id!r}.")
            height, width = image.shape[:2]
            if width <= 0 or height <= 0:
                raise InputDataError(
                    f"Decoded opaque frame {planned.frame_id!r} has invalid dimensions."
                )
            encode_extension = ".jpg" if image_format is ImageFormat.JPEG else ".png"
            encoded_ok, encoded = cv2.imencode(encode_extension, image)
            if not encoded_ok:
                raise InputDataError(f"Unable to encode opaque frame {planned.frame_id!r}.")
            content = encoded.tobytes()
            image_relative_path = f"images/{planned.split.value}/{planned.frame_id}{extension}"
            destination = output_root / _relative_workspace_path(image_relative_path)
            status = _write_or_verify_image(destination, content, frame_id=planned.frame_id)
            actual_msec = capture.get(cv2.CAP_PROP_POS_MSEC)
            actual_seconds = actual_msec / 1000.0 if actual_msec >= 0 else None
            records.append(
                ExtractedFrameRecord(
                    frame_id=planned.frame_id,
                    clip_id=planned.clip_id,
                    split=planned.split,
                    image_relative_path=image_relative_path,
                    planned_timestamp_seconds=planned.planned_timestamp_seconds,
                    actual_timestamp_seconds=actual_seconds,
                    width=int(width),
                    height=int(height),
                    checksum_sha256=hashlib.sha256(content).hexdigest(),
                    status=status,
                )
            )
    finally:
        capture.release()
    return records


def _relative_workspace_path(value: str) -> Path:
    """Convert a controlled POSIX workspace path to a platform path."""

    return Path(*value.split("/"))


def _write_or_verify_image(
    destination: Path,
    content: bytes,
    *,
    frame_id: str,
) -> ExtractedFrameStatus:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        try:
            existing = destination.read_bytes()
        except OSError as exc:
            raise InputDataError(f"Unable to verify existing opaque frame {frame_id!r}.") from exc
        if existing != content:
            raise InputDataError(
                f"Existing opaque frame {frame_id!r} differs; refusing to overwrite it."
            )
        return ExtractedFrameStatus.EXISTING_VERIFIED
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(destination)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise InputDataError(f"Unable to write opaque frame {frame_id!r}.") from exc
    return ExtractedFrameStatus.EXTRACTED


def _prepare_output_structure(root: Path) -> None:
    try:
        for split in DatasetSplit:
            (root / "images" / split.value).mkdir(parents=True, exist_ok=True)
            (root / "labels" / split.value).mkdir(parents=True, exist_ok=True)
        (root / "metadata").mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InputDataError("Unable to prepare the local annotation workspace.") from exc


def _require_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:
        raise DependencyUnavailableError("OpenCV is required for local frame extraction.") from exc
    return cv2


def _load_json_object(path: str | Path, *, description: str) -> dict[str, Any]:
    input_path = Path(path)
    if not input_path.is_file():
        raise InputDataError(f"The {description} is missing or is not a file.")
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InputDataError(f"The {description} is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise InputDataError(f"The {description} must contain one JSON object.")
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
    "ExtractedFrameRecord",
    "ExtractedFrameStatus",
    "FrameExtractionReport",
    "ImageFormat",
    "extract_frames",
    "load_local_source_map",
    "run_extraction",
    "write_extraction_report",
]
