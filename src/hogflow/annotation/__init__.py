"""Framework-neutral local pig-annotation preparation contracts."""

from hogflow.annotation.models import (
    AnnotationDatasetManifest,
    AnnotationFrameRecord,
    AnnotationStatus,
    DatasetSplit,
    FrameAnnotation,
    ManifestValidationStatus,
    PigAnnotation,
)
from hogflow.annotation.policy import normalized_pig_box_from_pixels
from hogflow.annotation.yolo import parse_yolo, serialize_yolo

__all__ = [
    "AnnotationDatasetManifest",
    "AnnotationFrameRecord",
    "AnnotationStatus",
    "DatasetSplit",
    "FrameAnnotation",
    "ManifestValidationStatus",
    "PigAnnotation",
    "normalized_pig_box_from_pixels",
    "parse_yolo",
    "serialize_yolo",
]
