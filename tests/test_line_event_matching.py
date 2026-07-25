from datetime import timezone

import pytest
from _phase6_helpers import BASE_TIME

from hogflow.counting import (
    LineSide,
    LiveCrossingDirection,
    LiveCrossingEvent,
    NormalizedPoint,
)
from hogflow.evaluation import GroundTruthCrossingEvent, match_crossing_events
from hogflow.evaluation.line_errors import GroundTruthMatchingError


def _predicted(
    frame: int,
    tracker_id: int = 1,
    *,
    direction: LiveCrossingDirection = LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
) -> LiveCrossingEvent:
    previous_side, current_side = (
        (LineSide.NEGATIVE, LineSide.POSITIVE)
        if direction is LiveCrossingDirection.NEGATIVE_TO_POSITIVE
        else (LineSide.POSITIVE, LineSide.NEGATIVE)
    )
    return LiveCrossingEvent(
        source_id="synthetic-source",
        tracker_lifecycle_id="lifecycle",
        tracker_id=tracker_id,
        frame_sequence=frame,
        previous_frame_sequence=max(0, frame - 1),
        captured_at=BASE_TIME.astimezone(timezone.utc),
        direction=direction,
        previous_side=previous_side,
        current_side=current_side,
        previous_point=NormalizedPoint(0.4, 0.5),
        representative_point=NormalizedPoint(0.6, 0.5),
        line_id="line",
        configuration_fingerprint="a" * 64,
    )


def _truth(
    identifier: str,
    frame: int,
    *,
    direction: LiveCrossingDirection | None = LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
) -> GroundTruthCrossingEvent:
    return GroundTruthCrossingEvent(
        event_id=identifier,
        frame_start=frame,
        frame_end=frame,
        direction=direction,
        provenance="synthetic-reference",
    )


def test_exact_and_windowed_matches_report_offsets() -> None:
    metrics = match_crossing_events(
        (_predicted(10), _predicted(22, 2)),
        (_truth("exact", 10), _truth("window", 20)),
        maximum_frame_offset=2,
        require_direction_match=True,
    )

    assert metrics.true_positives == 2
    assert metrics.false_positives == 0
    assert metrics.false_negatives == 0
    assert metrics.mean_absolute_frame_offset == 1
    assert metrics.median_absolute_frame_offset == 1
    assert metrics.precision == metrics.recall == metrics.f1_score == 1


def test_outside_window_is_false_positive_and_false_negative() -> None:
    metrics = match_crossing_events(
        (_predicted(20),),
        (_truth("reference", 10),),
        maximum_frame_offset=2,
        require_direction_match=True,
    )

    assert (metrics.true_positives, metrics.false_positives, metrics.false_negatives) == (
        0,
        1,
        1,
    )
    assert metrics.mean_absolute_frame_offset is None


def test_direction_policy_can_reject_or_diagnose_mismatch() -> None:
    prediction = _predicted(
        10,
        direction=LiveCrossingDirection.POSITIVE_TO_NEGATIVE,
    )
    reference = _truth("reference", 10)

    strict = match_crossing_events(
        (prediction,),
        (reference,),
        maximum_frame_offset=0,
        require_direction_match=True,
    )
    diagnostic = match_crossing_events(
        (prediction,),
        (reference,),
        maximum_frame_offset=0,
        require_direction_match=False,
    )

    assert strict.true_positives == 0
    assert diagnostic.true_positives == 1
    assert diagnostic.direction_error_count == 1
    assert diagnostic.direction_correct_count == 0


def test_matching_is_one_to_one_for_duplicate_predictions_and_references() -> None:
    predictions = (_predicted(10, 2), _predicted(10, 1))
    references = (_truth("reference-b", 10), _truth("reference-a", 10))

    metrics = match_crossing_events(
        predictions,
        references,
        maximum_frame_offset=0,
        require_direction_match=True,
    )

    assert metrics.true_positives == 2
    assert tuple(match.predicted_tracker_id for match in metrics.matches) == (1, 2)
    assert tuple(match.ground_truth_event_id for match in metrics.matches) == (
        "reference-a",
        "reference-b",
    )


@pytest.mark.parametrize(
    "predictions,references,expected",
    (
        ((), (), (0, 0, 0)),
        ((_predicted(1),), (), (0, 1, 0)),
        ((), (_truth("reference", 1),), (0, 0, 1)),
    ),
)
def test_zero_safe_matching(
    predictions: tuple[LiveCrossingEvent, ...],
    references: tuple[GroundTruthCrossingEvent, ...],
    expected: tuple[int, int, int],
) -> None:
    metrics = match_crossing_events(
        predictions,
        references,
        maximum_frame_offset=0,
        require_direction_match=True,
    )

    assert (metrics.true_positives, metrics.false_positives, metrics.false_negatives) == expected
    assert metrics.precision == metrics.recall == metrics.f1_score == 0


def test_count_error_and_deterministic_greedy_tie_break() -> None:
    first = match_crossing_events(
        (_predicted(9, 2), _predicted(11, 1), _predicted(30, 3)),
        (_truth("reference", 10),),
        maximum_frame_offset=1,
        require_direction_match=True,
    )
    second = match_crossing_events(
        tuple(reversed((_predicted(9, 2), _predicted(11, 1), _predicted(30, 3)))),
        (_truth("reference", 10),),
        maximum_frame_offset=1,
        require_direction_match=True,
    )

    assert first == second
    assert first.matches[0].predicted_frame_sequence == 9
    assert first.exact_event_total_difference == 2
    assert first.absolute_event_count_error == 2


def test_matching_rejects_invalid_window() -> None:
    with pytest.raises(GroundTruthMatchingError):
        match_crossing_events((), (), maximum_frame_offset=-1, require_direction_match=True)
