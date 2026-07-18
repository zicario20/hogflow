"""Immutable framework-neutral models for local pig bounding-box annotation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
from re import fullmatch

from hogflow.core import InputDataError
from hogflow.evaluation.detection_models import CoordinateSpace, EvaluationBoundingBox

PIG_CLASS_ID = 0
PIG_CLASS_NAME = "pig"
ANNOTATION_POLICY_VERSION = "phase-4.2-v1"
_OPAQUE_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_-]*"
_CHECKSUM_PATTERN = r"[0-9a-f]{64}"


class AnnotationStatus(str, Enum):
    """Human-confirmed annotation state for one extracted frame."""

    ANNOTATED = "annotated"
    VERIFIED_EMPTY = "verified_empty"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"
    EXCLUDED = "excluded"


class DatasetSplit(str, Enum):
    """Source-video-level assignment for local dataset preparation."""

    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"
    PREPARATION = "preparation"


class ManifestValidationStatus(str, Enum):
    """Validation state recorded by a sanitized annotation manifest."""

    PENDING = "pending"
    VALID = "valid"
    INVALID = "invalid"


def validate_opaque_identifier(value: object, *, field_name: str) -> None:
    """Validate an identifier that cannot contain a path or private filename."""

    if not isinstance(value, str) or fullmatch(_OPAQUE_ID_PATTERN, value) is None:
        raise InputDataError(
            f"{field_name} must be an opaque identifier containing only letters, numbers, "
            "underscores, or hyphens."
        )


def validate_phase4_identifier(value: object, *, field_name: str) -> None:
    """Validate a 24-character hash-derived Phase 4 clip or frame ID."""

    if not isinstance(value, str) or fullmatch(r"[0-9a-f]{24}", value) is None:
        raise InputDataError(
            f"{field_name} must be a 24-character lowercase hexadecimal opaque ID."
        )


def validate_relative_workspace_path(value: object, *, field_name: str) -> None:
    """Validate one sanitized path relative to the annotation workspace."""

    if not isinstance(value, str) or not value or "\\" in value:
        raise InputDataError(f"{field_name} must be a non-empty POSIX relative path.")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or any(part.endswith(":") for part in path.parts):
        raise InputDataError(f"{field_name} must not be absolute or traverse parent directories.")


@dataclass(frozen=True, slots=True)
class PigAnnotation:
    """One normalized YOLO-compatible box for the single ``pig`` class."""

    bounding_box: EvaluationBoundingBox
    class_id: int = PIG_CLASS_ID

    def __post_init__(self) -> None:
        if self.class_id != PIG_CLASS_ID or isinstance(self.class_id, bool):
            raise InputDataError("Phase 4.2 supports only class ID 0 (pig).")
        if not isinstance(self.bounding_box, EvaluationBoundingBox):
            raise InputDataError("Pig annotation bounding_box must be EvaluationBoundingBox.")
        if self.bounding_box.coordinate_space is not CoordinateSpace.NORMALIZED:
            raise InputDataError("Pig annotation coordinates must be normalized.")


@dataclass(frozen=True, slots=True)
class FrameAnnotation:
    """Human annotation state and immutable boxes for one opaque frame ID."""

    frame_id: str
    status: AnnotationStatus
    boxes: tuple[PigAnnotation, ...] = ()

    def __post_init__(self) -> None:
        validate_phase4_identifier(self.frame_id, field_name="frame_id")
        if not isinstance(self.status, AnnotationStatus):
            raise InputDataError("status must be an AnnotationStatus value.")
        if not isinstance(self.boxes, tuple) or not all(
            isinstance(box, PigAnnotation) for box in self.boxes
        ):
            raise InputDataError("boxes must be an immutable PigAnnotation tuple.")
        if len(set(self.boxes)) != len(self.boxes):
            raise InputDataError("Duplicate pig annotation boxes are forbidden.")
        if self.status is AnnotationStatus.ANNOTATED and not self.boxes:
            raise InputDataError("An annotated frame must contain at least one pig box.")
        if self.status is not AnnotationStatus.ANNOTATED and self.boxes:
            raise InputDataError(
                "Only frames with annotated status may contain pig bounding boxes."
            )


@dataclass(frozen=True, slots=True)
class AnnotationFrameRecord:
    """One sanitized frame record retained in a local dataset manifest."""

    frame_id: str
    clip_id: str
    split: DatasetSplit
    image_relative_path: str
    width: int
    height: int
    annotation_status: AnnotationStatus
    bounding_box_count: int
    checksum_sha256: str
    validation_status: ManifestValidationStatus = ManifestValidationStatus.PENDING

    def __post_init__(self) -> None:
        validate_phase4_identifier(self.frame_id, field_name="frame_id")
        validate_phase4_identifier(self.clip_id, field_name="clip_id")
        if not isinstance(self.split, DatasetSplit):
            raise InputDataError("split must be a DatasetSplit value.")
        validate_relative_workspace_path(
            self.image_relative_path,
            field_name="image_relative_path",
        )
        if not self.image_relative_path.startswith(f"images/{self.split.value}/"):
            raise InputDataError("image_relative_path must agree with the frame split.")
        image_path = PurePosixPath(self.image_relative_path)
        if image_path.stem != self.frame_id or image_path.suffix.lower() not in {
            ".jpg",
            ".jpeg",
            ".png",
        }:
            raise InputDataError(
                "Manifest image names must use only the opaque frame ID and a supported extension."
            )
        for field_name in ("width", "height"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise InputDataError(f"{field_name} must be a positive integer.")
        if not isinstance(self.annotation_status, AnnotationStatus):
            raise InputDataError("annotation_status must be an AnnotationStatus value.")
        if (
            not isinstance(self.bounding_box_count, int)
            or isinstance(self.bounding_box_count, bool)
            or self.bounding_box_count < 0
        ):
            raise InputDataError("bounding_box_count must be a non-negative integer.")
        if self.annotation_status is AnnotationStatus.ANNOTATED and self.bounding_box_count == 0:
            raise InputDataError("Annotated frame records require a positive box count.")
        if (
            self.annotation_status is not AnnotationStatus.ANNOTATED
            and self.bounding_box_count != 0
        ):
            raise InputDataError("Only annotated frame records may have a positive box count.")
        if (
            not isinstance(self.checksum_sha256, str)
            or fullmatch(_CHECKSUM_PATTERN, self.checksum_sha256) is None
        ):
            raise InputDataError("checksum_sha256 must be 64 lowercase hexadecimal characters.")
        if not isinstance(self.validation_status, ManifestValidationStatus):
            raise InputDataError("validation_status must be a ManifestValidationStatus value.")


@dataclass(frozen=True, slots=True)
class AnnotationDatasetManifest:
    """Sanitized deterministic manifest containing no source paths or private notes."""

    schema_version: int
    dataset_id: str
    annotation_policy_version: str
    class_map: tuple[tuple[int, str], ...]
    frames: tuple[AnnotationFrameRecord, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1 or isinstance(self.schema_version, bool):
            raise InputDataError("Annotation manifest schema_version must be 1.")
        validate_opaque_identifier(self.dataset_id, field_name="dataset_id")
        if (
            not isinstance(self.annotation_policy_version, str)
            or not self.annotation_policy_version.strip()
        ):
            raise InputDataError("annotation_policy_version must be non-empty.")
        if self.class_map != ((PIG_CLASS_ID, PIG_CLASS_NAME),):
            raise InputDataError("Phase 4.2 class_map must be exactly ((0, 'pig'),).")
        if not isinstance(self.frames, tuple) or not all(
            isinstance(frame, AnnotationFrameRecord) for frame in self.frames
        ):
            raise InputDataError("frames must be an immutable AnnotationFrameRecord tuple.")
        frame_ids = tuple(frame.frame_id for frame in self.frames)
        if tuple(sorted(frame_ids)) != frame_ids or len(set(frame_ids)) != len(frame_ids):
            raise InputDataError("Manifest frames must have unique IDs in sorted order.")


__all__ = [
    "ANNOTATION_POLICY_VERSION",
    "PIG_CLASS_ID",
    "PIG_CLASS_NAME",
    "AnnotationDatasetManifest",
    "AnnotationFrameRecord",
    "AnnotationStatus",
    "DatasetSplit",
    "FrameAnnotation",
    "ManifestValidationStatus",
    "PigAnnotation",
    "validate_opaque_identifier",
    "validate_phase4_identifier",
    "validate_relative_workspace_path",
]
