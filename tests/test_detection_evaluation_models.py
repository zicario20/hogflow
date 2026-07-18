from dataclasses import FrozenInstanceError

import pytest

from hogflow.core import InputDataError
from hogflow.evaluation.detection_models import (
    CoordinateSpace,
    DetectionClassSummary,
    DetectionDatasetSummary,
    DetectionEvaluationResult,
    DetectionFrame,
    EvaluationBoundingBox,
    GroundTruthDetection,
    PredictedDetection,
)
from hogflow.models import BoundingBox


def _box(
    x_min: float = 0,
    y_min: float = 0,
    x_max: float = 10,
    y_max: float = 10,
    *,
    space: CoordinateSpace = CoordinateSpace.PIXEL,
) -> EvaluationBoundingBox:
    return EvaluationBoundingBox(
        bounding_box=BoundingBox(x_min, y_min, x_max, y_max),
        coordinate_space=space,
    )


def test_evaluation_models_are_frozen_and_slotted() -> None:
    detection = GroundTruthDetection(detection_id="pig-001", bounding_box=_box())

    with pytest.raises(FrozenInstanceError):
        detection.class_name = "other"  # type: ignore[misc]

    assert not hasattr(detection, "__dict__")
    assert detection.class_name == "pig"


def test_evaluation_box_reuses_canonical_bounding_box() -> None:
    canonical = BoundingBox(1, 2, 8, 9)
    evaluation = EvaluationBoundingBox(canonical, CoordinateSpace.PIXEL)

    assert evaluation.bounding_box is canonical
    assert evaluation.coordinate_space is CoordinateSpace.PIXEL


@pytest.mark.parametrize(
    "coordinates, space",
    [
        ((-1, 0, 1, 1), CoordinateSpace.PIXEL),
        ((0, 0, 1.1, 1), CoordinateSpace.NORMALIZED),
    ],
)
def test_evaluation_box_rejects_invalid_coordinate_ranges(
    coordinates: tuple[float, float, float, float],
    space: CoordinateSpace,
) -> None:
    with pytest.raises(InputDataError):
        _box(*coordinates, space=space)


def test_canonical_box_rejects_zero_or_negative_area() -> None:
    with pytest.raises(InputDataError):
        BoundingBox(0, 0, 0, 1)
    with pytest.raises(InputDataError):
        BoundingBox(2, 0, 1, 1)


@pytest.mark.parametrize("confidence", [-0.1, 1.1, float("nan")])
def test_prediction_rejects_invalid_confidence(confidence: float) -> None:
    with pytest.raises(InputDataError):
        PredictedDetection(
            detection_id="prediction-1",
            bounding_box=_box(),
            confidence=confidence,
        )


def test_frame_rejects_pixel_box_outside_dimensions() -> None:
    ground_truth = GroundTruthDetection(
        detection_id="pig-1",
        bounding_box=_box(x_max=101),
    )

    with pytest.raises(InputDataError, match="inside"):
        DetectionFrame(
            source_video_id="source-1",
            frame_id="frame-1",
            width=100,
            height=100,
            ground_truth=(ground_truth,),
        )


def test_frame_accepts_normalized_box_and_explicit_pig_label() -> None:
    frame = DetectionFrame(
        source_video_id="source-1",
        frame_id="frame-1",
        width=1920,
        height=1080,
        ground_truth=(
            GroundTruthDetection(
                detection_id="pig-1",
                bounding_box=_box(0.1, 0.2, 0.5, 0.8, space=CoordinateSpace.NORMALIZED),
                class_name="pig",
            ),
        ),
    )

    assert frame.ground_truth[0].class_name == "pig"


def test_frame_rejects_path_like_source_identifiers_and_duplicate_ids() -> None:
    with pytest.raises(InputDataError, match="opaque"):
        DetectionFrame(
            source_video_id="private/video.mp4",
            frame_id="frame-1",
            width=100,
            height=100,
        )

    duplicate = GroundTruthDetection(detection_id="pig-1", bounding_box=_box())
    with pytest.raises(InputDataError, match="unique"):
        DetectionFrame(
            source_video_id="source-1",
            frame_id="frame-1",
            width=100,
            height=100,
            ground_truth=(duplicate, duplicate),
        )


def test_dataset_summary_validates_sorted_class_totals() -> None:
    summary = DetectionDatasetSummary(
        source_video_count=1,
        frame_count=2,
        ground_truth_count=3,
        prediction_count=2,
        classes=(DetectionClassSummary("pig", 3, 2),),
    )
    assert summary.classes[0].class_name == "pig"

    with pytest.raises(InputDataError, match="totals"):
        DetectionDatasetSummary(
            source_video_count=1,
            frame_count=2,
            ground_truth_count=4,
            prediction_count=2,
            classes=(DetectionClassSummary("pig", 3, 2),),
        )


def test_evaluation_result_rejects_metrics_inconsistent_with_counts() -> None:
    with pytest.raises(InputDataError, match="precision"):
        DetectionEvaluationResult(
            iou_threshold=0.5,
            evaluated_frame_count=1,
            matches=(),
            true_positives=0,
            false_positives=1,
            false_negatives=1,
            precision=1.0,
            recall=0.0,
            f1_score=0.0,
        )
