"""Framework-neutral failure summaries for a baseline pig detector."""

from __future__ import annotations

from collections.abc import Sequence

from hogflow.core import InputDataError
from hogflow.evaluation import (
    CoordinateSpace,
    DetectionEvaluationResult,
    DetectionFrame,
    bounding_box_area,
)
from hogflow.training.models import FailureAnalysisSummary


def summarize_detection_failures(
    frames: Sequence[DetectionFrame],
    result: DetectionEvaluationResult,
    *,
    small_object_area_ratio: float,
) -> FailureAnalysisSummary:
    """Summarize observable baseline failures without inventing occlusion labels.

    Very small pigs are ground-truth boxes whose area is at or below the
    configured fraction of frame area. Empty-frame false positives are all
    predictions on human-verified empty frames. Phase 4.2 has no occlusion
    severity field, so heavy-occlusion counts remain explicitly unavailable.
    """

    frame_tuple = tuple(frames)
    if not all(isinstance(frame, DetectionFrame) for frame in frame_tuple):
        raise InputDataError("frames must contain only DetectionFrame values.")
    if not isinstance(result, DetectionEvaluationResult):
        raise InputDataError("result must be DetectionEvaluationResult.")
    if result.evaluated_frame_count != len(frame_tuple):
        raise InputDataError("Evaluation result frame count does not match failure-analysis input.")
    if (
        not isinstance(small_object_area_ratio, (int, float))
        or isinstance(small_object_area_ratio, bool)
        or not 0.0 < float(small_object_area_ratio) <= 1.0
    ):
        raise InputDataError("small_object_area_ratio must be greater than 0 and at most 1.")

    very_small = 0
    empty_frames = 0
    empty_false_positives = 0
    for frame in frame_tuple:
        if not frame.ground_truth:
            empty_frames += 1
            empty_false_positives += len(frame.predictions)
        for detection in frame.ground_truth:
            area = bounding_box_area(detection.bounding_box)
            if detection.bounding_box.coordinate_space is CoordinateSpace.PIXEL:
                area /= frame.width * frame.height
            if area <= float(small_object_area_ratio):
                very_small += 1

    return FailureAnalysisSummary(
        false_positive_count=result.false_positives,
        false_negative_count=result.false_negatives,
        very_small_ground_truth_count=very_small,
        empty_frame_count=empty_frames,
        empty_frame_false_positive_count=empty_false_positives,
        heavy_occlusion_count=None,
        notes=(
            "Heavy-occlusion totals are unavailable because Phase 4.2 annotations do not encode occlusion severity.",
            "Failure counts are detector diagnostics and do not establish counting accuracy.",
        ),
    )


__all__ = ["summarize_detection_failures"]
