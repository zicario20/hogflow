"""Immutable framework-neutral models for future pig-detector evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from re import fullmatch
from typing import Iterable

from hogflow.core import InputDataError
from hogflow.models import BoundingBox

_OPAQUE_IDENTIFIER_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]*"


class CoordinateSpace(str, Enum):
    """Coordinate system used by an evaluation bounding box."""

    PIXEL = "pixel"
    NORMALIZED = "normalized"


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_probability(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        and 0.0 <= value <= 1.0
    )


def _validate_identifier(value: object, *, field_name: str) -> None:
    if not isinstance(value, str) or fullmatch(_OPAQUE_IDENTIFIER_PATTERN, value) is None:
        raise InputDataError(
            f"{field_name} must be an opaque identifier containing only letters, numbers, "
            "periods, underscores, or hyphens."
        )


def _validate_class_name(value: object) -> None:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise InputDataError("Detection class_name must be a non-empty trimmed string.")


@dataclass(frozen=True, slots=True)
class EvaluationBoundingBox:
    """A canonical box with an explicit pixel or normalized coordinate space.

    Pixel coordinates must be non-negative and are checked against frame bounds
    by :class:`DetectionFrame`. Normalized coordinates must remain in ``[0, 1]``.
    The wrapped canonical :class:`hogflow.models.BoundingBox` guarantees finite,
    positive-area geometry.
    """

    bounding_box: BoundingBox
    coordinate_space: CoordinateSpace

    def __post_init__(self) -> None:
        if not isinstance(self.bounding_box, BoundingBox):
            raise InputDataError("Evaluation bounding_box must be a canonical BoundingBox.")
        if not isinstance(self.coordinate_space, CoordinateSpace):
            raise InputDataError("coordinate_space must be a CoordinateSpace value.")
        coordinates = (
            self.bounding_box.x_min,
            self.bounding_box.y_min,
            self.bounding_box.x_max,
            self.bounding_box.y_max,
        )
        if any(coordinate < 0 for coordinate in coordinates):
            raise InputDataError("Evaluation bounding-box coordinates must be non-negative.")
        if self.coordinate_space is CoordinateSpace.NORMALIZED and any(
            coordinate > 1 for coordinate in coordinates
        ):
            raise InputDataError("Normalized bounding-box coordinates must not exceed 1.")


@dataclass(frozen=True, slots=True)
class GroundTruthDetection:
    """One human-provided reference detection for a single frame."""

    detection_id: str
    bounding_box: EvaluationBoundingBox
    class_name: str = "pig"

    def __post_init__(self) -> None:
        _validate_identifier(self.detection_id, field_name="Ground-truth detection_id")
        if not isinstance(self.bounding_box, EvaluationBoundingBox):
            raise InputDataError(
                "GroundTruthDetection bounding_box must be an EvaluationBoundingBox."
            )
        _validate_class_name(self.class_name)


@dataclass(frozen=True, slots=True)
class PredictedDetection:
    """One framework-neutral detector prediction for a single frame."""

    detection_id: str
    bounding_box: EvaluationBoundingBox
    confidence: float
    class_name: str = "pig"

    def __post_init__(self) -> None:
        _validate_identifier(self.detection_id, field_name="Predicted detection_id")
        if not isinstance(self.bounding_box, EvaluationBoundingBox):
            raise InputDataError(
                "PredictedDetection bounding_box must be an EvaluationBoundingBox."
            )
        if not _is_probability(self.confidence):
            raise InputDataError("Prediction confidence must be between 0 and 1.")
        _validate_class_name(self.class_name)


@dataclass(frozen=True, slots=True)
class DetectionFrame:
    """Ground truth and predictions for one frame from one opaque source-video ID.

    ``source_video_id`` exists so future data splits can remain isolated at the
    source-video level. It is an opaque ID, never a path or private filename.
    Detection IDs must be unique within their respective frame collections.
    """

    source_video_id: str
    frame_id: str
    width: int
    height: int
    ground_truth: tuple[GroundTruthDetection, ...] = ()
    predictions: tuple[PredictedDetection, ...] = ()

    def __post_init__(self) -> None:
        _validate_identifier(self.source_video_id, field_name="source_video_id")
        _validate_identifier(self.frame_id, field_name="frame_id")
        if not _is_integer(self.width) or self.width <= 0:
            raise InputDataError("DetectionFrame width must be a positive integer.")
        if not _is_integer(self.height) or self.height <= 0:
            raise InputDataError("DetectionFrame height must be a positive integer.")
        if not isinstance(self.ground_truth, tuple) or not all(
            isinstance(item, GroundTruthDetection) for item in self.ground_truth
        ):
            raise InputDataError("ground_truth must be an immutable detection tuple.")
        if not isinstance(self.predictions, tuple) or not all(
            isinstance(item, PredictedDetection) for item in self.predictions
        ):
            raise InputDataError("predictions must be an immutable detection tuple.")
        _validate_unique_ids(
            (item.detection_id for item in self.ground_truth),
            description="ground-truth detection",
        )
        _validate_unique_ids(
            (item.detection_id for item in self.predictions),
            description="predicted detection",
        )
        for item in (*self.ground_truth, *self.predictions):
            _validate_frame_bounds(item.bounding_box, width=self.width, height=self.height)


@dataclass(frozen=True, slots=True)
class DetectionMatch:
    """One deterministic prediction-to-ground-truth match."""

    source_video_id: str
    frame_id: str
    prediction_id: str
    ground_truth_id: str
    iou: float

    def __post_init__(self) -> None:
        _validate_identifier(self.source_video_id, field_name="source_video_id")
        _validate_identifier(self.frame_id, field_name="frame_id")
        _validate_identifier(self.prediction_id, field_name="prediction_id")
        _validate_identifier(self.ground_truth_id, field_name="ground_truth_id")
        if not _is_probability(self.iou):
            raise InputDataError("DetectionMatch iou must be between 0 and 1.")


@dataclass(frozen=True, slots=True)
class DetectionEvaluationResult:
    """Aggregate detection counts and metrics at one explicit IoU threshold."""

    iou_threshold: float
    evaluated_frame_count: int
    matches: tuple[DetectionMatch, ...]
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float

    def __post_init__(self) -> None:
        if not _is_probability(self.iou_threshold) or self.iou_threshold == 0:
            raise InputDataError("iou_threshold must be greater than 0 and at most 1.")
        for field_name in (
            "evaluated_frame_count",
            "true_positives",
            "false_positives",
            "false_negatives",
        ):
            value = getattr(self, field_name)
            if not _is_integer(value) or value < 0:
                raise InputDataError(f"{field_name} must be a non-negative integer.")
        if not isinstance(self.matches, tuple) or not all(
            isinstance(match, DetectionMatch) for match in self.matches
        ):
            raise InputDataError("matches must be an immutable DetectionMatch tuple.")
        if len(self.matches) != self.true_positives:
            raise InputDataError("true_positives must equal the number of matches.")
        for field_name in ("precision", "recall", "f1_score"):
            if not _is_probability(getattr(self, field_name)):
                raise InputDataError(f"{field_name} must be between 0 and 1.")
        _validate_unique_match_endpoints(self.matches)
        if any(match.iou + 1e-12 < self.iou_threshold for match in self.matches):
            raise InputDataError("Every match must satisfy iou_threshold.")
        expected_precision = _ratio_or_zero(
            self.true_positives,
            self.true_positives + self.false_positives,
        )
        expected_recall = _ratio_or_zero(
            self.true_positives,
            self.true_positives + self.false_negatives,
        )
        expected_f1 = _ratio_or_zero(
            2 * expected_precision * expected_recall,
            expected_precision + expected_recall,
        )
        expected_metrics = (
            ("precision", self.precision, expected_precision),
            ("recall", self.recall, expected_recall),
            ("f1_score", self.f1_score, expected_f1),
        )
        for field_name, actual, expected in expected_metrics:
            if abs(actual - expected) > 1e-12:
                raise InputDataError(f"{field_name} is inconsistent with detection counts.")


@dataclass(frozen=True, slots=True)
class DetectionClassSummary:
    """Ground-truth and prediction totals for one class label."""

    class_name: str
    ground_truth_count: int
    prediction_count: int

    def __post_init__(self) -> None:
        _validate_class_name(self.class_name)
        for field_name in ("ground_truth_count", "prediction_count"):
            value = getattr(self, field_name)
            if not _is_integer(value) or value < 0:
                raise InputDataError(f"{field_name} must be a non-negative integer.")


@dataclass(frozen=True, slots=True)
class DetectionDatasetSummary:
    """Deterministic structural totals for an evaluation dataset."""

    source_video_count: int
    frame_count: int
    ground_truth_count: int
    prediction_count: int
    classes: tuple[DetectionClassSummary, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "source_video_count",
            "frame_count",
            "ground_truth_count",
            "prediction_count",
        ):
            value = getattr(self, field_name)
            if not _is_integer(value) or value < 0:
                raise InputDataError(f"{field_name} must be a non-negative integer.")
        if not isinstance(self.classes, tuple) or not all(
            isinstance(item, DetectionClassSummary) for item in self.classes
        ):
            raise InputDataError("classes must be an immutable DetectionClassSummary tuple.")
        class_names = tuple(item.class_name for item in self.classes)
        if tuple(sorted(class_names)) != class_names or len(set(class_names)) != len(class_names):
            raise InputDataError("classes must be unique and sorted by class_name.")
        if sum(item.ground_truth_count for item in self.classes) != self.ground_truth_count:
            raise InputDataError("Class ground-truth totals must equal ground_truth_count.")
        if sum(item.prediction_count for item in self.classes) != self.prediction_count:
            raise InputDataError("Class prediction totals must equal prediction_count.")
        if self.source_video_count > self.frame_count:
            raise InputDataError("source_video_count must not exceed frame_count.")


def _validate_unique_ids(values: Iterable[str], *, description: str) -> None:
    identifiers = tuple(values)
    if len(set(identifiers)) != len(identifiers):
        raise InputDataError(f"Each {description} ID must be unique within a frame.")


def _validate_frame_bounds(
    evaluation_box: EvaluationBoundingBox,
    *,
    width: int,
    height: int,
) -> None:
    if evaluation_box.coordinate_space is not CoordinateSpace.PIXEL:
        return
    box = evaluation_box.bounding_box
    if box.x_max > width or box.y_max > height:
        raise InputDataError("Pixel bounding box must remain inside DetectionFrame dimensions.")


def _validate_unique_match_endpoints(matches: tuple[DetectionMatch, ...]) -> None:
    prediction_keys = {
        (match.source_video_id, match.frame_id, match.prediction_id) for match in matches
    }
    ground_truth_keys = {
        (match.source_video_id, match.frame_id, match.ground_truth_id) for match in matches
    }
    if len(prediction_keys) != len(matches) or len(ground_truth_keys) != len(matches):
        raise InputDataError("Detection matches must be one-to-one within each frame.")


def _ratio_or_zero(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
