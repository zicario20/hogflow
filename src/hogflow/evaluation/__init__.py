"""Framework-neutral foundations for pig-detector dataset preparation and evaluation."""

from hogflow.evaluation.detection_metrics import (
    bounding_box_area,
    evaluate_detections,
    f1_score,
    intersection_area,
    intersection_over_union,
    precision,
    recall,
    summarize_detection_dataset,
    union_area,
)
from hogflow.evaluation.detection_models import (
    CoordinateSpace,
    DetectionClassSummary,
    DetectionDatasetSummary,
    DetectionEvaluationResult,
    DetectionFrame,
    DetectionMatch,
    EvaluationBoundingBox,
    GroundTruthDetection,
    PredictedDetection,
)

__all__ = [
    "CoordinateSpace",
    "DetectionClassSummary",
    "DetectionDatasetSummary",
    "DetectionEvaluationResult",
    "DetectionFrame",
    "DetectionMatch",
    "EvaluationBoundingBox",
    "GroundTruthDetection",
    "PredictedDetection",
    "bounding_box_area",
    "evaluate_detections",
    "f1_score",
    "intersection_area",
    "intersection_over_union",
    "precision",
    "recall",
    "summarize_detection_dataset",
    "union_area",
]
