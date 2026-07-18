"""Immutable framework-neutral models for Phase 3 video dataset inventory."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from pathlib import PurePosixPath

from hogflow.core import ConfigurationError, InputDataError


class CameraStabilityLabel(str, Enum):
    """Conservative labels produced by bounded automatic camera-motion estimation."""

    LIKELY_STATIC = "likely_static"
    LOW_MOTION = "low_motion"
    MOVING_CAMERA = "moving_camera"
    UNKNOWN = "unknown"


class SuitabilityLabel(str, Enum):
    """Inventory-only labels that do not claim model or counting quality."""

    DETECTION_CANDIDATE = "detection_candidate"
    TRACKING_CANDIDATE = "tracking_candidate"
    COUNTING_CANDIDATE = "counting_candidate"
    STRESS_TEST_CANDIDATE = "stress_test_candidate"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"


_ALLOWED_INTENDED_USES = frozenset({"detection", "tracking", "counting", "stress_test"})
_ALLOWED_SOURCE_TYPES = frozenset(
    {
        "licensed",
        "other_authorized",
        "public_domain",
        "research_dataset",
        "self_recorded",
        "synthetic",
    }
)


def _is_non_negative_finite(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        and value >= 0
    )


def _validate_relative_path(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise InputDataError(f"{field_name} must be a non-empty relative path.")
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    has_drive_prefix = bool(path.parts and path.parts[0].endswith(":"))
    if path.is_absolute() or has_drive_prefix or ".." in path.parts:
        raise InputDataError(f"{field_name} must not be absolute or contain parent traversal.")


@dataclass(frozen=True, slots=True)
class ManualReviewMetadata:
    """Human review and authorization facts loaded from a local sidecar file."""

    authorized_for_project: bool
    source_type: str
    source_reference: str
    license_or_permission_notes: str
    camera_static_confirmed: bool | None
    clear_passage_confirmed: bool | None
    predominant_direction_confirmed: bool | None
    counting_line_possible: bool | None
    intended_use: tuple[str, ...]
    reviewer_notes: str

    def __post_init__(self) -> None:
        if not isinstance(self.authorized_for_project, bool):
            raise InputDataError("authorized_for_project must be true or false.")
        if self.source_type not in _ALLOWED_SOURCE_TYPES:
            raise InputDataError(
                "source_type must be one of: " + ", ".join(sorted(_ALLOWED_SOURCE_TYPES))
            )
        for field_name in ("source_reference", "license_or_permission_notes"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise InputDataError(f"{field_name} must be a non-empty string.")
        for field_name in (
            "camera_static_confirmed",
            "clear_passage_confirmed",
            "predominant_direction_confirmed",
            "counting_line_possible",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, bool):
                raise InputDataError(f"{field_name} must be true, false, or null.")
        if not isinstance(self.intended_use, tuple) or not all(
            isinstance(item, str) for item in self.intended_use
        ):
            raise InputDataError("intended_use must be an immutable sequence of strings.")
        unknown_uses = set(self.intended_use) - _ALLOWED_INTENDED_USES
        if unknown_uses:
            raise InputDataError(
                "Unsupported intended_use values: " + ", ".join(sorted(unknown_uses))
            )
        if len(set(self.intended_use)) != len(self.intended_use):
            raise InputDataError("intended_use must not contain duplicate values.")
        if not isinstance(self.reviewer_notes, str):
            raise InputDataError("reviewer_notes must be a string.")


@dataclass(frozen=True, slots=True)
class VideoFileMetadata:
    """One local video's metadata without OpenCV or NumPy values.

    Invalid or unavailable numeric properties are represented by ``None`` and
    explained in ``validation_errors``. Automatic stability and suitability
    labels are inventory aids only; they are not evidence of detector,
    tracking, or counting performance.
    """

    relative_path: str
    file_size_bytes: int
    container_extension: str
    duration_seconds: float | None
    fps: float | None
    frame_count: int | None
    width: int | None
    height: int | None
    codec: str | None
    readable: bool
    validation_errors: tuple[str, ...] = ()
    sampled_frame_count: int = 0
    stability_score_percent: float | None = None
    stability_label: CameraStabilityLabel = CameraStabilityLabel.UNKNOWN
    suitability_labels: tuple[SuitabilityLabel, ...] = (SuitabilityLabel.NEEDS_MANUAL_REVIEW,)
    review_metadata: ManualReviewMetadata | None = None

    def __post_init__(self) -> None:
        _validate_relative_path(self.relative_path, field_name="relative_path")
        if not isinstance(self.file_size_bytes, int) or isinstance(self.file_size_bytes, bool):
            raise InputDataError("file_size_bytes must be a non-negative integer.")
        if self.file_size_bytes < 0:
            raise InputDataError("file_size_bytes must be a non-negative integer.")
        if (
            not isinstance(self.container_extension, str)
            or not self.container_extension.startswith(".")
            or self.container_extension != self.container_extension.lower()
        ):
            raise InputDataError("container_extension must be a lowercase extension with a dot.")
        for field_name in ("duration_seconds", "fps", "stability_score_percent"):
            value = getattr(self, field_name)
            if value is not None and not _is_non_negative_finite(value):
                raise InputDataError(f"{field_name} must be finite and non-negative when present.")
        for field_name in ("frame_count", "width", "height", "sampled_frame_count"):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, int) or isinstance(value, bool) or value < 0
            ):
                raise InputDataError(f"{field_name} must be a non-negative integer when present.")
        if self.codec is not None and not isinstance(self.codec, str):
            raise InputDataError("codec must be a string or None.")
        if not isinstance(self.readable, bool):
            raise InputDataError("readable must be true or false.")
        if not isinstance(self.validation_errors, tuple) or not all(
            isinstance(error, str) and error for error in self.validation_errors
        ):
            raise InputDataError("validation_errors must be an immutable sequence of strings.")
        if not isinstance(self.stability_label, CameraStabilityLabel):
            raise InputDataError("stability_label must be a CameraStabilityLabel.")
        if not isinstance(self.suitability_labels, tuple) or not all(
            isinstance(label, SuitabilityLabel) for label in self.suitability_labels
        ):
            raise InputDataError("suitability_labels must contain SuitabilityLabel values.")
        if self.review_metadata is not None and not isinstance(
            self.review_metadata, ManualReviewMetadata
        ):
            raise InputDataError("review_metadata must be ManualReviewMetadata or None.")


@dataclass(frozen=True, slots=True)
class ClipManifestEntry:
    """One manually selected clip boundary recorded without cutting video."""

    original_source_reference: str
    clip_filename: str
    start_time_seconds: float
    end_time_seconds: float
    reason_selected: str
    camera_appears_static: bool | None
    notes: str

    def __post_init__(self) -> None:
        for field_name in ("original_source_reference", "reason_selected"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise InputDataError(f"{field_name} must be a non-empty string.")
        _validate_relative_path(self.clip_filename, field_name="clip_filename")
        if not _is_non_negative_finite(self.start_time_seconds):
            raise InputDataError("start_time_seconds must be finite and non-negative.")
        if not _is_non_negative_finite(self.end_time_seconds):
            raise InputDataError("end_time_seconds must be finite and non-negative.")
        if self.end_time_seconds <= self.start_time_seconds:
            raise InputDataError("end_time_seconds must be greater than start_time_seconds.")
        if self.camera_appears_static is not None and not isinstance(
            self.camera_appears_static, bool
        ):
            raise InputDataError("camera_appears_static must be true, false, or null.")
        if not isinstance(self.notes, str):
            raise InputDataError("notes must be a string.")


@dataclass(frozen=True, slots=True)
class DatasetInventorySummary:
    """Immutable aggregate summary for one local inventory run."""

    total_files: int
    readable_files: int
    unreadable_files: int
    total_duration_seconds: float
    total_size_bytes: int
    resolution_distribution: tuple[tuple[str, int], ...]
    stability_counts: tuple[tuple[str, int], ...]
    suitability_counts: tuple[tuple[str, int], ...]
    fps_min: float | None = None
    fps_max: float | None = None

    def __post_init__(self) -> None:
        for field_name in ("total_files", "readable_files", "unreadable_files", "total_size_bytes"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise InputDataError(f"{field_name} must be a non-negative integer.")
        if self.readable_files + self.unreadable_files != self.total_files:
            raise InputDataError("Readable and unreadable totals must equal total_files.")
        if not _is_non_negative_finite(self.total_duration_seconds):
            raise InputDataError("total_duration_seconds must be finite and non-negative.")
        for field_name in ("fps_min", "fps_max"):
            value = getattr(self, field_name)
            if value is not None and not _is_non_negative_finite(value):
                raise InputDataError(f"{field_name} must be finite and non-negative.")
        for field_name in (
            "resolution_distribution",
            "stability_counts",
            "suitability_counts",
        ):
            entries = getattr(self, field_name)
            if not isinstance(entries, tuple) or not all(
                isinstance(entry, tuple)
                and len(entry) == 2
                and isinstance(entry[0], str)
                and isinstance(entry[1], int)
                and entry[1] >= 0
                for entry in entries
            ):
                raise InputDataError(f"{field_name} must contain immutable label/count pairs.")


@dataclass(frozen=True, slots=True)
class DatasetInventory:
    """One immutable collection of file metadata, summary, and optional clip manifest."""

    files: tuple[VideoFileMetadata, ...]
    summary: DatasetInventorySummary
    clip_manifest: tuple[ClipManifestEntry, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.files, tuple) or not all(
            isinstance(item, VideoFileMetadata) for item in self.files
        ):
            raise InputDataError("files must contain immutable VideoFileMetadata values.")
        if not isinstance(self.summary, DatasetInventorySummary):
            raise InputDataError("summary must be a DatasetInventorySummary.")
        if self.summary.total_files != len(self.files):
            raise InputDataError("summary.total_files must equal the number of files.")
        if not isinstance(self.clip_manifest, tuple) or not all(
            isinstance(item, ClipManifestEntry) for item in self.clip_manifest
        ):
            raise InputDataError("clip_manifest must contain immutable ClipManifestEntry values.")


@dataclass(frozen=True, slots=True)
class VideoInspectionSettings:
    """Bounded video sampling and stability thresholds for metadata inspection."""

    sample_frame_count: int = 12
    static_threshold_percent: float = 0.10
    moving_threshold_percent: float = 0.75
    minimum_motion_features: int = 8
    minimum_motion_pairs: int = 2
    max_sample_dimension: int = 640

    def __post_init__(self) -> None:
        for field_name in (
            "sample_frame_count",
            "minimum_motion_features",
            "minimum_motion_pairs",
            "max_sample_dimension",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ConfigurationError(f"{field_name} must be a positive integer.")
        if not _is_non_negative_finite(self.static_threshold_percent):
            raise ConfigurationError("static_threshold_percent must be finite and non-negative.")
        if not _is_non_negative_finite(self.moving_threshold_percent):
            raise ConfigurationError("moving_threshold_percent must be finite and non-negative.")
        if self.static_threshold_percent >= self.moving_threshold_percent:
            raise ConfigurationError(
                "static_threshold_percent must be lower than moving_threshold_percent."
            )


@dataclass(frozen=True, slots=True)
class SuitabilitySettings:
    """Conservative minimum durations used only for inventory candidate labels."""

    minimum_detection_duration_seconds: float = 2.0
    minimum_tracking_duration_seconds: float = 5.0

    def __post_init__(self) -> None:
        if not _is_non_negative_finite(self.minimum_detection_duration_seconds):
            raise ConfigurationError(
                "minimum_detection_duration_seconds must be finite and non-negative."
            )
        if not _is_non_negative_finite(self.minimum_tracking_duration_seconds):
            raise ConfigurationError(
                "minimum_tracking_duration_seconds must be finite and non-negative."
            )
        if self.minimum_tracking_duration_seconds < self.minimum_detection_duration_seconds:
            raise ConfigurationError(
                "minimum_tracking_duration_seconds must not be shorter than detection duration."
            )
