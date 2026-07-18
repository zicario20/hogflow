"""Local prepared-dataset validation with sanitized deterministic reports."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from hogflow.annotation.manifest import load_annotation_manifest
from hogflow.annotation.models import (
    AnnotationDatasetManifest,
    AnnotationFrameRecord,
    AnnotationStatus,
    DatasetSplit,
    validate_opaque_identifier,
    validate_phase4_identifier,
)
from hogflow.annotation.yolo import parse_yolo
from hogflow.core import (
    DependencyUnavailableError,
    HogFlowError,
    InputDataError,
    configure_logging,
    get_logger,
)

LOGGER = get_logger(__name__)
SUPPORTED_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})


class FindingSeverity(str, Enum):
    """Severity assigned to a deterministic annotation-validation finding."""

    ERROR = "error"
    WARNING = "warning"
    INFORMATIONAL = "informational"


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """One sanitized issue identified without local source information."""

    severity: FindingSeverity
    code: str
    message: str
    frame_id: str | None = None
    clip_id: str | None = None
    relative_path: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.severity, FindingSeverity):
            raise InputDataError("severity must be FindingSeverity.")
        for field_name in ("code", "message"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise InputDataError(f"{field_name} must be non-empty text.")
        for field_name in ("frame_id", "clip_id"):
            value = getattr(self, field_name)
            if value is not None:
                validate_phase4_identifier(value, field_name=field_name)
        if self.relative_path is not None:
            path = PurePosixPath(self.relative_path)
            if path.is_absolute() or ".." in path.parts or "\\" in self.relative_path:
                raise InputDataError("Finding relative_path must remain workspace-relative.")


@dataclass(frozen=True, slots=True)
class AnnotationValidationReport:
    """Sanitized aggregate validation result."""

    dataset_id: str
    manifest_frame_count: int
    discovered_image_count: int
    discovered_label_count: int
    findings: tuple[ValidationFinding, ...]

    def __post_init__(self) -> None:
        validate_opaque_identifier(self.dataset_id, field_name="dataset_id")
        for field_name in (
            "manifest_frame_count",
            "discovered_image_count",
            "discovered_label_count",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise InputDataError(f"{field_name} must be a non-negative integer.")
        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, ValidationFinding) for finding in self.findings
        ):
            raise InputDataError("findings must be an immutable ValidationFinding tuple.")
        if tuple(sorted(self.findings, key=_finding_sort_key)) != self.findings:
            raise InputDataError("findings must use deterministic sorted order.")

    @property
    def error_count(self) -> int:
        """Return the number of fatal findings."""

        return sum(finding.severity is FindingSeverity.ERROR for finding in self.findings)

    @property
    def warning_count(self) -> int:
        """Return the number of warning findings."""

        return sum(finding.severity is FindingSeverity.WARNING for finding in self.findings)

    @property
    def informational_count(self) -> int:
        """Return the number of informational findings."""

        return sum(finding.severity is FindingSeverity.INFORMATIONAL for finding in self.findings)

    @property
    def valid(self) -> bool:
        """Return whether no fatal annotation error was found."""

        return self.error_count == 0


def validate_annotation_dataset(
    dataset_root: str | Path,
    manifest: AnnotationDatasetManifest,
) -> AnnotationValidationReport:
    """Validate a prepared local YOLO dataset without exposing source paths."""

    if not isinstance(manifest, AnnotationDatasetManifest):
        raise InputDataError("manifest must be AnnotationDatasetManifest.")
    root = Path(dataset_root)
    findings: list[ValidationFinding] = []
    images = _discover_images(root, findings)
    labels = _discover_labels(root, findings)
    records = {frame.frame_id: frame for frame in manifest.frames}

    _validate_source_split_isolation(manifest.frames, findings)
    _validate_duplicate_frame_locations(images, findings)
    _validate_orphan_and_unregistered_files(images, labels, records, findings)

    content_hashes: dict[str, list[tuple[str, DatasetSplit]]] = {}
    for record in manifest.frames:
        image_paths = images.get(record.frame_id, ())
        expected_image = root / Path(*record.image_relative_path.split("/"))
        if len(image_paths) != 1 or image_paths[0] != expected_image:
            findings.append(
                _finding(
                    FindingSeverity.ERROR,
                    "missing_or_misplaced_image",
                    "Manifest image is missing or not stored at its sanitized split path.",
                    record,
                    record.image_relative_path,
                )
            )
            continue
        content = _validate_image(expected_image, record, findings)
        if content is not None:
            digest = hashlib.sha256(content).hexdigest()
            content_hashes.setdefault(digest, []).append((record.frame_id, record.split))
        _validate_label(root, record, labels, findings)

    _validate_duplicate_content(content_hashes, findings)
    if not findings:
        findings.append(
            ValidationFinding(
                severity=FindingSeverity.INFORMATIONAL,
                code="dataset_validation_passed",
                message="No annotation dataset issue was detected.",
            )
        )
    return AnnotationValidationReport(
        dataset_id=manifest.dataset_id,
        manifest_frame_count=len(manifest.frames),
        discovered_image_count=sum(len(paths) for paths in images.values()),
        discovered_label_count=sum(len(paths) for paths in labels.values()),
        findings=tuple(sorted(findings, key=_finding_sort_key)),
    )


def write_validation_reports(
    report: AnnotationValidationReport,
    output_json: str | Path,
) -> tuple[Path, Path, Path]:
    """Write deterministic JSON, CSV, and Markdown reports atomically."""

    if not isinstance(report, AnnotationValidationReport):
        raise InputDataError("report must be AnnotationValidationReport.")
    json_path = Path(output_json)
    csv_path = json_path.with_suffix(".csv")
    markdown_path = json_path.with_suffix(".md")
    payload = _report_to_dict(report)
    _atomic_write_text(
        json_path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )
    _atomic_write_text(csv_path, _report_csv(report))
    _atomic_write_text(markdown_path, _report_markdown(report))
    return json_path, csv_path, markdown_path


def run_validation(
    *,
    dataset_root: str | Path,
    manifest_path: str | Path,
    output_path: str | Path,
) -> AnnotationValidationReport:
    """Load a manifest, validate the local dataset, and write all reports."""

    report = validate_annotation_dataset(
        dataset_root,
        load_annotation_manifest(manifest_path),
    )
    write_validation_reports(report, output_path)
    return report


def build_parser() -> argparse.ArgumentParser:
    """Create the local annotation-validation CLI parser."""

    parser = argparse.ArgumentParser(description="Validate a local prepared YOLO pig dataset.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run annotation validation and return a process status code."""

    configure_logging()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    manifest_path = arguments.manifest or (arguments.dataset / "metadata" / "dataset_manifest.json")
    try:
        report = run_validation(
            dataset_root=arguments.dataset,
            manifest_path=manifest_path,
            output_path=arguments.output,
        )
    except HogFlowError as exc:
        parser.error(str(exc))
    LOGGER.info(
        "Annotation validation complete: %d errors, %d warnings",
        report.error_count,
        report.warning_count,
    )
    return 0 if report.valid else 1


def _discover_images(
    root: Path,
    findings: list[ValidationFinding],
) -> dict[str, tuple[Path, ...]]:
    image_root = root / "images"
    found: dict[str, list[Path]] = {}
    if not image_root.is_dir():
        findings.append(
            ValidationFinding(
                FindingSeverity.ERROR,
                "missing_images_directory",
                "The prepared dataset has no images directory.",
            )
        )
        return {}
    for path in sorted(item for item in image_root.rglob("*") if item.is_file()):
        if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            findings.append(
                ValidationFinding(
                    FindingSeverity.WARNING,
                    "unexpected_image_file",
                    "Unexpected file found below the images directory.",
                )
            )
            continue
        found.setdefault(path.stem, []).append(path)
    return {frame_id: tuple(paths) for frame_id, paths in found.items()}


def _discover_labels(
    root: Path,
    findings: list[ValidationFinding],
) -> dict[str, tuple[Path, ...]]:
    label_root = root / "labels"
    found: dict[str, list[Path]] = {}
    if not label_root.is_dir():
        findings.append(
            ValidationFinding(
                FindingSeverity.ERROR,
                "missing_labels_directory",
                "The prepared dataset has no labels directory.",
            )
        )
        return {}
    for path in sorted(item for item in label_root.rglob("*") if item.is_file()):
        if path.suffix.lower() != ".txt":
            findings.append(
                ValidationFinding(
                    FindingSeverity.WARNING,
                    "unexpected_label_file",
                    "Unexpected file found below the labels directory.",
                )
            )
            continue
        found.setdefault(path.stem, []).append(path)
    return {frame_id: tuple(paths) for frame_id, paths in found.items()}


def _validate_source_split_isolation(
    frames: Sequence[AnnotationFrameRecord],
    findings: list[ValidationFinding],
) -> None:
    split_by_clip: dict[str, DatasetSplit] = {}
    reported: set[str] = set()
    for frame in frames:
        previous = split_by_clip.setdefault(frame.clip_id, frame.split)
        if previous is not frame.split and frame.clip_id not in reported:
            findings.append(
                _finding(
                    FindingSeverity.ERROR,
                    "source_video_split_leakage",
                    "One opaque source clip appears in more than one dataset split.",
                    frame,
                )
            )
            reported.add(frame.clip_id)


def _validate_duplicate_frame_locations(
    images: Mapping[str, tuple[Path, ...]],
    findings: list[ValidationFinding],
) -> None:
    for frame_id, paths in images.items():
        if len(paths) > 1:
            findings.append(
                ValidationFinding(
                    FindingSeverity.ERROR,
                    "duplicate_frame_id",
                    "An opaque frame ID appears in multiple image locations.",
                    frame_id=_safe_phase4_id(frame_id),
                )
            )


def _validate_orphan_and_unregistered_files(
    images: Mapping[str, tuple[Path, ...]],
    labels: Mapping[str, tuple[Path, ...]],
    records: Mapping[str, AnnotationFrameRecord],
    findings: list[ValidationFinding],
) -> None:
    for frame_id in sorted(set(images) - set(records)):
        findings.append(
            ValidationFinding(
                FindingSeverity.ERROR,
                "missing_annotation_status",
                "Image has no explicit annotation status in the manifest.",
                frame_id=_safe_phase4_id(frame_id),
            )
        )
    for frame_id in sorted(set(labels) - set(images)):
        findings.append(
            ValidationFinding(
                FindingSeverity.ERROR,
                "orphan_label",
                "YOLO label has no matching image.",
                frame_id=_safe_phase4_id(frame_id),
            )
        )
    for frame_id, paths in labels.items():
        if len(paths) > 1:
            findings.append(
                ValidationFinding(
                    FindingSeverity.ERROR,
                    "duplicate_label_id",
                    "An opaque frame ID has more than one label file.",
                    frame_id=_safe_phase4_id(frame_id),
                )
            )


def _validate_image(
    path: Path,
    record: AnnotationFrameRecord,
    findings: list[ValidationFinding],
) -> bytes | None:
    try:
        content = path.read_bytes()
    except OSError:
        findings.append(
            _finding(
                FindingSeverity.ERROR,
                "unreadable_image",
                "Image bytes cannot be read.",
                record,
                record.image_relative_path,
            )
        )
        return None
    cv2 = _require_cv2()
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None or getattr(image, "size", 0) == 0:
        findings.append(
            _finding(
                FindingSeverity.ERROR,
                "unreadable_image",
                "Image cannot be decoded.",
                record,
                record.image_relative_path,
            )
        )
        return content
    height, width = image.shape[:2]
    if int(width) != record.width or int(height) != record.height:
        findings.append(
            _finding(
                FindingSeverity.ERROR,
                "image_dimension_mismatch",
                "Decoded image dimensions differ from the manifest.",
                record,
                record.image_relative_path,
            )
        )
    if hashlib.sha256(content).hexdigest() != record.checksum_sha256:
        findings.append(
            _finding(
                FindingSeverity.ERROR,
                "image_checksum_mismatch",
                "Image checksum differs from the manifest.",
                record,
                record.image_relative_path,
            )
        )
    return content


def _validate_label(
    root: Path,
    record: AnnotationFrameRecord,
    labels: Mapping[str, tuple[Path, ...]],
    findings: list[ValidationFinding],
) -> None:
    paths = labels.get(record.frame_id, ())
    expected_relative = f"labels/{record.split.value}/{record.frame_id}.txt"
    expected_path = root / Path(*expected_relative.split("/"))
    if record.annotation_status in {
        AnnotationStatus.NEEDS_MANUAL_REVIEW,
        AnnotationStatus.EXCLUDED,
    }:
        if paths:
            findings.append(
                _finding(
                    FindingSeverity.ERROR,
                    "label_for_unready_frame",
                    "Review or excluded frame must not have a YOLO label.",
                    record,
                    expected_relative,
                )
            )
        return
    if len(paths) != 1 or paths[0] != expected_path:
        findings.append(
            _finding(
                FindingSeverity.ERROR,
                "missing_or_misplaced_label",
                "Finalized frame requires one YOLO label at its assigned split path.",
                record,
                expected_relative,
            )
        )
        return
    try:
        text = expected_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        findings.append(
            _finding(
                FindingSeverity.ERROR,
                "unreadable_label",
                "YOLO label is not readable UTF-8 text.",
                record,
                expected_relative,
            )
        )
        return
    try:
        annotation = parse_yolo(
            text,
            frame_id=record.frame_id,
            status=record.annotation_status,
        )
    except InputDataError:
        findings.append(
            _finding(
                FindingSeverity.ERROR,
                "invalid_yolo_label",
                "YOLO label is malformed, duplicated, out of bounds, or status-inconsistent.",
                record,
                expected_relative,
            )
        )
        return
    if len(annotation.boxes) != record.bounding_box_count:
        findings.append(
            _finding(
                FindingSeverity.ERROR,
                "bounding_box_count_mismatch",
                "Manifest bounding-box count differs from the YOLO label.",
                record,
                expected_relative,
            )
        )


def _validate_duplicate_content(
    content_hashes: Mapping[str, list[tuple[str, DatasetSplit]]],
    findings: list[ValidationFinding],
) -> None:
    for duplicate_group in content_hashes.values():
        if len(duplicate_group) < 2:
            continue
        splits = {split for _frame_id, split in duplicate_group}
        severity = FindingSeverity.ERROR if len(splits) > 1 else FindingSeverity.WARNING
        code = "duplicate_content_across_splits" if len(splits) > 1 else "duplicate_content"
        for frame_id, _split in sorted(duplicate_group):
            findings.append(
                ValidationFinding(
                    severity,
                    code,
                    "Duplicate image content was found in the prepared dataset.",
                    frame_id=frame_id,
                )
            )


def _finding(
    severity: FindingSeverity,
    code: str,
    message: str,
    record: AnnotationFrameRecord,
    relative_path: str | None = None,
) -> ValidationFinding:
    return ValidationFinding(
        severity=severity,
        code=code,
        message=message,
        frame_id=record.frame_id,
        clip_id=record.clip_id,
        relative_path=relative_path,
    )


def _finding_sort_key(finding: ValidationFinding) -> tuple[str, ...]:
    severity_order = {
        FindingSeverity.ERROR: "0",
        FindingSeverity.WARNING: "1",
        FindingSeverity.INFORMATIONAL: "2",
    }
    return (
        severity_order[finding.severity],
        finding.code,
        finding.clip_id or "",
        finding.frame_id or "",
        finding.relative_path or "",
        finding.message,
    )


def _safe_phase4_id(value: str) -> str | None:
    try:
        validate_phase4_identifier(value, field_name="frame_id")
    except InputDataError:
        return None
    return value


def _report_to_dict(report: AnnotationValidationReport) -> dict[str, Any]:
    return {
        "dataset_id": report.dataset_id,
        "findings": [
            {
                "clip_id": finding.clip_id,
                "code": finding.code,
                "frame_id": finding.frame_id,
                "message": finding.message,
                "relative_path": finding.relative_path,
                "severity": finding.severity.value,
            }
            for finding in report.findings
        ],
        "format_version": 1,
        "summary": {
            "discovered_image_count": report.discovered_image_count,
            "discovered_label_count": report.discovered_label_count,
            "error_count": report.error_count,
            "informational_count": report.informational_count,
            "manifest_frame_count": report.manifest_frame_count,
            "valid": report.valid,
            "warning_count": report.warning_count,
        },
    }


def _report_csv(report: AnnotationValidationReport) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("severity", "code", "clip_id", "frame_id", "relative_path", "message"))
    for finding in report.findings:
        writer.writerow(
            (
                finding.severity.value,
                finding.code,
                finding.clip_id or "",
                finding.frame_id or "",
                finding.relative_path or "",
                finding.message,
            )
        )
    return output.getvalue()


def _report_markdown(report: AnnotationValidationReport) -> str:
    lines = [
        "# HogFlow Annotation Validation",
        "",
        f"Dataset ID: `{report.dataset_id}`",
        "",
        f"Status: **{'VALID' if report.valid else 'INVALID'}**",
        "",
        f"- Manifest frames: {report.manifest_frame_count}",
        f"- Discovered images: {report.discovered_image_count}",
        f"- Discovered labels: {report.discovered_label_count}",
        f"- Errors: {report.error_count}",
        f"- Warnings: {report.warning_count}",
        f"- Informational: {report.informational_count}",
        "",
        "## Findings",
        "",
    ]
    for finding in report.findings:
        subject = finding.frame_id or "dataset"
        lines.append(
            f"- **{finding.severity.value}** `{finding.code}` ({subject}): {finding.message}"
        )
    lines.extend(
        [
            "",
            "This local report validates structure only; it does not establish annotation or model quality.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        raise InputDataError("Unable to write sanitized annotation validation output.") from exc


def _require_cv2() -> Any:
    try:
        import cv2
    except ImportError as exc:
        raise DependencyUnavailableError("OpenCV is required to validate local images.") from exc
    return cv2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AnnotationValidationReport",
    "FindingSeverity",
    "SUPPORTED_IMAGE_EXTENSIONS",
    "ValidationFinding",
    "run_validation",
    "validate_annotation_dataset",
    "write_validation_reports",
]
