"""Deterministic framework-neutral detection geometry, matching, and metrics."""

from __future__ import annotations

from collections import Counter
from math import isfinite
from typing import Sequence

from hogflow.core import ConfigurationError, InputDataError
from hogflow.evaluation.detection_models import (
    DetectionClassSummary,
    DetectionDatasetSummary,
    DetectionEvaluationResult,
    DetectionFrame,
    DetectionMatch,
    EvaluationBoundingBox,
)


def bounding_box_area(box: EvaluationBoundingBox) -> float:
    """Return positive box area in its declared coordinate-space units."""

    _validate_box(box)
    geometry = box.bounding_box
    return (geometry.x_max - geometry.x_min) * (geometry.y_max - geometry.y_min)


def intersection_area(first: EvaluationBoundingBox, second: EvaluationBoundingBox) -> float:
    """Return overlap area, or zero when two boxes do not overlap."""

    _validate_compatible_boxes(first, second)
    first_box = first.bounding_box
    second_box = second.bounding_box
    width = max(
        0.0, min(first_box.x_max, second_box.x_max) - max(first_box.x_min, second_box.x_min)
    )
    height = max(
        0.0,
        min(first_box.y_max, second_box.y_max) - max(first_box.y_min, second_box.y_min),
    )
    return width * height


def union_area(first: EvaluationBoundingBox, second: EvaluationBoundingBox) -> float:
    """Return combined area after subtracting overlap."""

    return bounding_box_area(first) + bounding_box_area(second) - intersection_area(first, second)


def intersection_over_union(first: EvaluationBoundingBox, second: EvaluationBoundingBox) -> float:
    """Return IoU in ``[0, 1]`` for boxes using the same coordinate space."""

    intersection = intersection_area(first, second)
    union = union_area(first, second)
    return intersection / union if union > 0 else 0.0


def precision(true_positives: int, false_positives: int) -> float:
    """Return precision, defined as zero when no predictions exist."""

    _validate_count(true_positives, name="true_positives")
    _validate_count(false_positives, name="false_positives")
    denominator = true_positives + false_positives
    return true_positives / denominator if denominator else 0.0


def recall(true_positives: int, false_negatives: int) -> float:
    """Return recall, defined as zero when no ground-truth objects exist."""

    _validate_count(true_positives, name="true_positives")
    _validate_count(false_negatives, name="false_negatives")
    denominator = true_positives + false_negatives
    return true_positives / denominator if denominator else 0.0


def f1_score(precision_value: float, recall_value: float) -> float:
    """Return harmonic mean, defined as zero when precision plus recall is zero."""

    for name, value in (("precision", precision_value), ("recall", recall_value)):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not isfinite(value)
            or not 0.0 <= value <= 1.0
        ):
            raise InputDataError(f"{name} must be between 0 and 1.")
    denominator = precision_value + recall_value
    return 2 * precision_value * recall_value / denominator if denominator else 0.0


def evaluate_detections(
    frames: Sequence[DetectionFrame],
    *,
    iou_threshold: float = 0.5,
) -> DetectionEvaluationResult:
    """Evaluate frames with deterministic confidence-first one-to-one matching.

    Frames are processed by opaque source and frame ID. Predictions are processed
    by descending confidence, then prediction ID. Each prediction takes the
    unmatched same-class ground truth with greatest IoU; equal-IoU candidates are
    resolved by ground-truth ID. This infrastructure computes no mAP.
    """

    threshold = _validate_iou_threshold(iou_threshold)
    frame_tuple = tuple(frames)
    if not all(isinstance(frame, DetectionFrame) for frame in frame_tuple):
        raise InputDataError("frames must contain only DetectionFrame values.")
    frame_keys = tuple((frame.source_video_id, frame.frame_id) for frame in frame_tuple)
    if len(set(frame_keys)) != len(frame_keys):
        raise InputDataError("DetectionFrame source/frame identifiers must be unique.")

    matches: list[DetectionMatch] = []
    false_positives = 0
    false_negatives = 0
    for frame in sorted(frame_tuple, key=lambda item: (item.source_video_id, item.frame_id)):
        frame_matches, frame_false_positives, frame_false_negatives = _match_frame(
            frame,
            threshold,
        )
        matches.extend(frame_matches)
        false_positives += frame_false_positives
        false_negatives += frame_false_negatives

    true_positives = len(matches)
    precision_value = precision(true_positives, false_positives)
    recall_value = recall(true_positives, false_negatives)
    return DetectionEvaluationResult(
        iou_threshold=threshold,
        evaluated_frame_count=len(frame_tuple),
        matches=tuple(matches),
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision_value,
        recall=recall_value,
        f1_score=f1_score(precision_value, recall_value),
    )


def summarize_detection_dataset(frames: Sequence[DetectionFrame]) -> DetectionDatasetSummary:
    """Return deterministic structural counts without claiming model quality."""

    frame_tuple = tuple(frames)
    if not all(isinstance(frame, DetectionFrame) for frame in frame_tuple):
        raise InputDataError("frames must contain only DetectionFrame values.")
    ground_truth_counts = Counter(
        detection.class_name for frame in frame_tuple for detection in frame.ground_truth
    )
    prediction_counts = Counter(
        detection.class_name for frame in frame_tuple for detection in frame.predictions
    )
    class_names = sorted(set(ground_truth_counts) | set(prediction_counts))
    classes = tuple(
        DetectionClassSummary(
            class_name=class_name,
            ground_truth_count=ground_truth_counts[class_name],
            prediction_count=prediction_counts[class_name],
        )
        for class_name in class_names
    )
    return DetectionDatasetSummary(
        source_video_count=len({frame.source_video_id for frame in frame_tuple}),
        frame_count=len(frame_tuple),
        ground_truth_count=sum(ground_truth_counts.values()),
        prediction_count=sum(prediction_counts.values()),
        classes=classes,
    )


def _match_frame(
    frame: DetectionFrame,
    threshold: float,
) -> tuple[list[DetectionMatch], int, int]:
    unmatched_ground_truth = {item.detection_id: item for item in frame.ground_truth}
    matches: list[DetectionMatch] = []
    predictions = sorted(
        frame.predictions,
        key=lambda item: (-item.confidence, item.detection_id),
    )
    for prediction in predictions:
        candidates: list[tuple[float, str]] = []
        for ground_truth_id, ground_truth in unmatched_ground_truth.items():
            if ground_truth.class_name != prediction.class_name:
                continue
            iou = intersection_over_union(prediction.bounding_box, ground_truth.bounding_box)
            if iou >= threshold:
                candidates.append((iou, ground_truth_id))
        if not candidates:
            continue
        iou, ground_truth_id = min(candidates, key=lambda item: (-item[0], item[1]))
        matches.append(
            DetectionMatch(
                source_video_id=frame.source_video_id,
                frame_id=frame.frame_id,
                prediction_id=prediction.detection_id,
                ground_truth_id=ground_truth_id,
                iou=iou,
            )
        )
        del unmatched_ground_truth[ground_truth_id]

    return (
        matches,
        len(frame.predictions) - len(matches),
        len(frame.ground_truth) - len(matches),
    )


def _validate_box(box: object) -> None:
    if not isinstance(box, EvaluationBoundingBox):
        raise InputDataError("Detection geometry requires EvaluationBoundingBox values.")


def _validate_compatible_boxes(first: object, second: object) -> None:
    if not isinstance(first, EvaluationBoundingBox) or not isinstance(
        second, EvaluationBoundingBox
    ):
        raise InputDataError("Detection geometry requires EvaluationBoundingBox values.")
    if first.coordinate_space is not second.coordinate_space:
        raise InputDataError("Bounding boxes must use the same coordinate space.")


def _validate_count(value: object, *, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InputDataError(f"{name} must be a non-negative integer.")


def _validate_iou_threshold(value: object) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or not 0.0 < value <= 1.0
    ):
        raise ConfigurationError("IoU threshold must be greater than 0 and at most 1.")
    return float(value)
