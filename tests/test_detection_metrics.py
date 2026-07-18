import pytest

from hogflow.core import ConfigurationError, InputDataError
from hogflow.evaluation import (
    CoordinateSpace,
    DetectionFrame,
    EvaluationBoundingBox,
    GroundTruthDetection,
    PredictedDetection,
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
from hogflow.models import BoundingBox


def _box(
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
    *,
    space: CoordinateSpace = CoordinateSpace.PIXEL,
) -> EvaluationBoundingBox:
    return EvaluationBoundingBox(BoundingBox(x_min, y_min, x_max, y_max), space)


def _ground_truth(identifier: str, box: EvaluationBoundingBox) -> GroundTruthDetection:
    return GroundTruthDetection(identifier, box)


def _prediction(
    identifier: str,
    box: EvaluationBoundingBox,
    confidence: float,
    *,
    class_name: str = "pig",
) -> PredictedDetection:
    return PredictedDetection(identifier, box, confidence, class_name)


def _frame(
    *,
    ground_truth: tuple[GroundTruthDetection, ...] = (),
    predictions: tuple[PredictedDetection, ...] = (),
    source_video_id: str = "source-1",
    frame_id: str = "frame-1",
) -> DetectionFrame:
    return DetectionFrame(
        source_video_id=source_video_id,
        frame_id=frame_id,
        width=100,
        height=100,
        ground_truth=ground_truth,
        predictions=predictions,
    )


def test_area_intersection_union_and_iou() -> None:
    first = _box(0, 0, 10, 10)
    second = _box(5, 5, 15, 15)

    assert bounding_box_area(first) == 100
    assert intersection_area(first, second) == 25
    assert union_area(first, second) == 175
    assert intersection_over_union(first, second) == pytest.approx(1 / 7)


def test_no_overlap_and_complete_overlap_iou() -> None:
    first = _box(0, 0, 10, 10)

    assert intersection_over_union(first, _box(20, 20, 30, 30)) == 0
    assert intersection_over_union(first, _box(0, 0, 10, 10)) == 1


def test_iou_rejects_mixed_coordinate_spaces() -> None:
    with pytest.raises(InputDataError, match="same coordinate"):
        intersection_over_union(
            _box(0, 0, 10, 10),
            _box(0, 0, 1, 1, space=CoordinateSpace.NORMALIZED),
        )


def test_duplicate_predictions_match_only_highest_confidence() -> None:
    target = _ground_truth("ground-1", _box(0, 0, 10, 10))
    low = _prediction("prediction-low", _box(0, 0, 10, 10), 0.4)
    high = _prediction("prediction-high", _box(0, 0, 10, 10), 0.9)

    result = evaluate_detections(
        (_frame(ground_truth=(target,), predictions=(low, high)),),
        iou_threshold=0.5,
    )

    assert result.true_positives == 1
    assert result.false_positives == 1
    assert result.false_negatives == 0
    assert result.matches[0].prediction_id == "prediction-high"
    assert result.precision == 0.5
    assert result.recall == 1.0


def test_equal_confidence_and_equal_iou_ties_use_lexical_ids() -> None:
    ground_a = _ground_truth("ground-a", _box(0, 0, 10, 10))
    ground_b = _ground_truth("ground-b", _box(0, 0, 10, 10))
    prediction_b = _prediction("prediction-b", _box(0, 0, 10, 10), 0.8)
    prediction_a = _prediction("prediction-a", _box(0, 0, 10, 10), 0.8)

    result = evaluate_detections(
        (
            _frame(
                ground_truth=(ground_b, ground_a),
                predictions=(prediction_b, prediction_a),
            ),
        )
    )

    assert tuple((match.prediction_id, match.ground_truth_id) for match in result.matches) == (
        ("prediction-a", "ground-a"),
        ("prediction-b", "ground-b"),
    )


def test_class_mismatch_does_not_match() -> None:
    frame = _frame(
        ground_truth=(_ground_truth("ground-1", _box(0, 0, 10, 10)),),
        predictions=(
            _prediction(
                "prediction-1",
                _box(0, 0, 10, 10),
                1.0,
                class_name="person",
            ),
        ),
    )

    result = evaluate_detections((frame,))

    assert result.true_positives == 0
    assert result.false_positives == 1
    assert result.false_negatives == 1


def test_zero_denominator_metric_behavior_is_explicit() -> None:
    assert precision(0, 0) == 0
    assert recall(0, 0) == 0
    assert f1_score(0, 0) == 0
    assert evaluate_detections(()).precision == 0
    assert evaluate_detections(()).recall == 0


def test_metrics_reject_invalid_counts_and_thresholds() -> None:
    with pytest.raises(InputDataError):
        precision(-1, 0)
    with pytest.raises(InputDataError):
        recall(0, -1)
    with pytest.raises(ConfigurationError):
        evaluate_detections((), iou_threshold=0)
    with pytest.raises(ConfigurationError):
        evaluate_detections((), iou_threshold=1.1)


def test_frame_order_does_not_change_matching_result() -> None:
    first = _frame(
        source_video_id="source-b",
        frame_id="frame-2",
        ground_truth=(_ground_truth("ground-b", _box(0, 0, 10, 10)),),
        predictions=(_prediction("prediction-b", _box(0, 0, 10, 10), 0.8),),
    )
    second = _frame(
        source_video_id="source-a",
        frame_id="frame-1",
        ground_truth=(_ground_truth("ground-a", _box(0, 0, 10, 10)),),
        predictions=(_prediction("prediction-a", _box(0, 0, 10, 10), 0.8),),
    )

    forward = evaluate_detections((first, second))
    reverse = evaluate_detections((second, first))

    assert forward == reverse
    assert tuple(match.source_video_id for match in forward.matches) == ("source-a", "source-b")


def test_dataset_summary_is_deterministic_and_class_aware() -> None:
    frame = _frame(
        ground_truth=(
            _ground_truth("pig-1", _box(0, 0, 10, 10)),
            GroundTruthDetection("person-1", _box(20, 20, 30, 30), "person"),
        ),
        predictions=(_prediction("pig-prediction", _box(0, 0, 10, 10), 0.9),),
    )

    summary = summarize_detection_dataset((frame,))

    assert summary.source_video_count == 1
    assert summary.frame_count == 1
    assert summary.ground_truth_count == 2
    assert tuple(item.class_name for item in summary.classes) == ("person", "pig")
