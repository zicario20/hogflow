"""Deterministic one-to-one matching for geometric crossing events."""

from __future__ import annotations

from collections.abc import Sequence
from statistics import median

from hogflow.counting import LiveCrossingEvent
from hogflow.evaluation.line_errors import GroundTruthMatchingError
from hogflow.evaluation.line_models import (
    CrossingEventMatch,
    CrossingEventMetrics,
    GroundTruthCrossingEvent,
)


def _event_key(event: LiveCrossingEvent) -> tuple[object, ...]:
    return (
        event.frame_sequence,
        event.tracker_lifecycle_id,
        event.tracker_id,
        event.direction.value,
        event.previous_frame_sequence,
    )


def _ground_truth_key(event: GroundTruthCrossingEvent) -> tuple[object, ...]:
    return (event.frame_start, event.frame_end, event.event_id)


def _distance_to_frame_window(frame_sequence: int, event: GroundTruthCrossingEvent) -> int:
    if frame_sequence < event.frame_start:
        return event.frame_start - frame_sequence
    if frame_sequence > event.frame_end:
        return frame_sequence - event.frame_end
    return 0


def match_crossing_events(
    predicted_events: Sequence[LiveCrossingEvent],
    ground_truth_events: Sequence[GroundTruthCrossingEvent],
    *,
    maximum_frame_offset: int,
    require_direction_match: bool,
) -> CrossingEventMetrics:
    """Match crossing events greedily by minimum frame distance.

    Eligible pairs are ordered by absolute distance, predicted-event identity,
    and ground-truth identity. Each endpoint may be used at most once. This
    deterministic greedy matcher is intentionally simple and is not a global
    assignment optimizer.
    """

    predicted = tuple(predicted_events)
    ground_truth = tuple(ground_truth_events)
    if not all(isinstance(event, LiveCrossingEvent) for event in predicted):
        raise GroundTruthMatchingError("Predicted crossings must be LiveCrossingEvent values.")
    if not all(isinstance(event, GroundTruthCrossingEvent) for event in ground_truth):
        raise GroundTruthMatchingError(
            "Ground-truth crossings must be GroundTruthCrossingEvent values."
        )
    if (
        not isinstance(maximum_frame_offset, int)
        or isinstance(maximum_frame_offset, bool)
        or maximum_frame_offset < 0
    ):
        raise GroundTruthMatchingError(
            "Maximum crossing-event frame offset must be a non-negative integer."
        )
    if not isinstance(require_direction_match, bool):
        raise GroundTruthMatchingError("Direction-match policy must be boolean.")

    predicted = tuple(sorted(predicted, key=_event_key))
    ground_truth = tuple(sorted(ground_truth, key=_ground_truth_key))
    predicted_keys = tuple(_event_key(event) for event in predicted)
    if len(set(predicted_keys)) != len(predicted_keys):
        raise GroundTruthMatchingError("Predicted crossing event identities must be unique.")
    ground_truth_ids = tuple(event.event_id for event in ground_truth)
    if len(set(ground_truth_ids)) != len(ground_truth_ids):
        raise GroundTruthMatchingError("Ground-truth crossing event IDs must be unique.")

    eligible: list[tuple[object, ...]] = []
    matching_operations = 0
    for predicted_index, prediction in enumerate(predicted):
        for ground_truth_index, reference in enumerate(ground_truth):
            matching_operations += 1
            offset = _distance_to_frame_window(prediction.frame_sequence, reference)
            if offset > maximum_frame_offset:
                continue
            direction_correct = (
                reference.direction is None or reference.direction is prediction.direction
            )
            if require_direction_match and not direction_correct:
                continue
            eligible.append(
                (
                    offset,
                    _event_key(prediction),
                    _ground_truth_key(reference),
                    predicted_index,
                    ground_truth_index,
                    direction_correct,
                )
            )

    used_predictions: set[int] = set()
    used_ground_truth: set[int] = set()
    matches: list[CrossingEventMatch] = []
    for (
        offset,
        _prediction_key,
        _reference_key,
        predicted_index,
        ground_truth_index,
        direction_correct,
    ) in sorted(eligible):
        if predicted_index in used_predictions or ground_truth_index in used_ground_truth:
            continue
        prediction = predicted[predicted_index]
        reference = ground_truth[ground_truth_index]
        used_predictions.add(predicted_index)
        used_ground_truth.add(ground_truth_index)
        matches.append(
            CrossingEventMatch(
                ground_truth_event_id=reference.event_id,
                predicted_frame_sequence=prediction.frame_sequence,
                predicted_tracker_lifecycle_id=prediction.tracker_lifecycle_id,
                predicted_tracker_id=prediction.tracker_id,
                absolute_frame_offset=int(offset),
                direction_correct=bool(direction_correct),
            )
        )

    matches.sort(
        key=lambda item: (
            item.predicted_frame_sequence,
            item.predicted_tracker_lifecycle_id,
            item.predicted_tracker_id,
            item.ground_truth_event_id,
        )
    )
    true_positives = len(matches)
    false_positives = len(predicted) - true_positives
    false_negatives = len(ground_truth) - true_positives
    precision = (
        true_positives / (true_positives + false_positives)
        if true_positives + false_positives
        else 0.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if true_positives + false_negatives
        else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    offsets = tuple(match.absolute_frame_offset for match in matches)
    exact_difference = len(predicted) - len(ground_truth)
    return CrossingEventMetrics(
        matches=tuple(matches),
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        precision=precision,
        recall=recall,
        f1_score=f1,
        mean_absolute_frame_offset=(sum(offsets) / len(offsets) if offsets else None),
        median_absolute_frame_offset=(float(median(offsets)) if offsets else None),
        direction_correct_count=sum(match.direction_correct for match in matches),
        direction_error_count=sum(not match.direction_correct for match in matches),
        exact_event_total_difference=exact_difference,
        absolute_event_count_error=abs(exact_difference),
        matching_operations=matching_operations,
    )


__all__ = ["match_crossing_events"]
