from dataclasses import replace

import pytest
from _phase7_helpers import (
    CROSSING_FINGERPRINT,
    counting_configuration,
    crossing_event,
    crossing_result,
)

from hogflow.core import InputDataError
from hogflow.counting import (
    CountingCapacityError,
    CountingDecisionType,
    CountingLifecycleError,
    CrossingCountingMismatchError,
    LifecycleDirectionalCounter,
    LiveCrossingDirection,
    StaleCountingRequestError,
)

POSITIVE = LiveCrossingDirection.NEGATIVE_TO_POSITIVE
REVERSE = LiveCrossingDirection.POSITIVE_TO_NEGATIVE


def _started_counter(**configuration_values) -> LifecycleDirectionalCounter:
    counter = LifecycleDirectionalCounter(counting_configuration(**configuration_values))
    counter.start("camera", "crossing-lifecycle-1")
    return counter


def _update(
    counter: LifecycleDirectionalCounter,
    frame: int,
    *events,
    lifecycle_id: str = "crossing-lifecycle-1",
):
    return counter.update(
        crossing_result(
            frame,
            tuple(events),
            lifecycle_id=lifecycle_id,
        )
    )


def test_start_is_idempotent_for_same_binding_and_rejects_mixed_source() -> None:
    counter = _started_counter()
    lifecycle_id = counter.counting_lifecycle_id

    counter.start("camera", "crossing-lifecycle-1")
    assert counter.counting_lifecycle_id == lifecycle_id
    with pytest.raises(CountingLifecycleError, match="mix"):
        counter.start("other", "crossing-lifecycle-1")


def test_update_and_reset_require_started_lifecycle_and_close_is_idempotent() -> None:
    counter = LifecycleDirectionalCounter(counting_configuration())

    with pytest.raises(CountingLifecycleError, match="started"):
        counter.update(crossing_result(1))
    with pytest.raises(CountingLifecycleError, match="started"):
        counter.reset("crossing-lifecycle-2")
    counter.start("camera", "crossing-lifecycle-1")
    counter.close()
    counter.close()
    assert not counter.is_started
    assert counter.statistics().closes == 1


def test_positive_simple_and_repeated_positive_count_once() -> None:
    counter = _started_counter()
    first = _update(counter, 1, crossing_event(1, 1, POSITIVE))
    second = _update(counter, 2, crossing_event(2, 1, POSITIVE))

    assert first.decisions[0].decision_type is CountingDecisionType.COUNTED_POSITIVE
    assert second.decisions[0].decision_type is (CountingDecisionType.IGNORED_DUPLICATE_POSITIVE)
    assert second.lifecycle_directional_count == 1


def test_reverse_before_positive_then_positive_counts_once() -> None:
    counter = _started_counter()
    reverse = _update(counter, 1, crossing_event(1, 1, REVERSE))
    positive = _update(counter, 2, crossing_event(2, 1, POSITIVE))

    assert reverse.decisions[0].decision_type is CountingDecisionType.IGNORED_REVERSE
    assert not reverse.decisions[0].identity_previously_counted
    assert positive.lifecycle_directional_count == 1


def test_positive_reverse_positive_remains_one() -> None:
    counter = _started_counter()
    _update(counter, 1, crossing_event(1, 1, POSITIVE))
    reverse = _update(counter, 2, crossing_event(2, 1, REVERSE))
    repeated = _update(counter, 3, crossing_event(3, 1, POSITIVE))

    assert reverse.decisions[0].identity_previously_counted
    assert reverse.lifecycle_directional_count == 1
    assert repeated.decisions[0].decision_type is (CountingDecisionType.IGNORED_DUPLICATE_POSITIVE)
    assert repeated.lifecycle_directional_count == 1


def test_reverse_only_never_increments() -> None:
    counter = _started_counter()
    first = _update(counter, 1, crossing_event(1, 1, REVERSE))
    second = _update(counter, 2, crossing_event(2, 1, REVERSE))

    assert first.frame_increments == second.frame_increments == 0
    assert second.lifecycle_directional_count == 0
    assert counter.statistics().reverses == 2


def test_two_tracks_and_duplicate_are_isolated() -> None:
    counter = _started_counter()
    first = _update(
        counter,
        1,
        crossing_event(1, 2, POSITIVE),
        crossing_event(1, 1, POSITIVE),
    )
    repeated = _update(counter, 2, crossing_event(2, 1, POSITIVE))

    assert [item.tracker_id for item in first.decisions] == [1, 2]
    assert first.frame_increments == 2
    assert first.lifecycle_directional_count == 2
    assert repeated.frame_increments == 0


def test_event_input_order_does_not_change_deterministic_decisions() -> None:
    first_counter = _started_counter()
    second_counter = _started_counter()
    event_one = crossing_event(1, 1, POSITIVE)
    event_two = crossing_event(1, 2, POSITIVE)

    first = _update(first_counter, 1, event_two, event_one)
    second = _update(second_counter, 1, event_one, event_two)

    first_values = tuple(
        (item.tracker_id, item.decision_type, item.total_before, item.total_after)
        for item in first.decisions
    )
    second_values = tuple(
        (item.tracker_id, item.decision_type, item.total_before, item.total_after)
        for item in second.decisions
    )
    assert first_values == second_values
    assert first.lifecycle_directional_count == second.lifecycle_directional_count == 2


def test_reset_creates_independent_total_for_same_numeric_tracker_id() -> None:
    counter = _started_counter()
    first = _update(counter, 1, crossing_event(1, 1, POSITIVE))
    first_counting_lifecycle = first.counting_lifecycle_id

    counter.reset("crossing-lifecycle-2")
    second_event = crossing_event(
        1,
        1,
        POSITIVE,
        lifecycle_id="crossing-lifecycle-2",
    )
    second = _update(
        counter,
        1,
        second_event,
        lifecycle_id="crossing-lifecycle-2",
    )

    assert second.counting_lifecycle_id != first_counting_lifecycle
    assert second.lifecycle_directional_count == 1
    assert counter.statistics().resets == 1


def test_gaps_are_valid_and_stale_or_repeated_frames_are_rejected() -> None:
    counter = _started_counter()
    result = _update(
        counter,
        10,
        crossing_event(
            10,
            1,
            POSITIVE,
            previous_frame_sequence=2,
        ),
    )

    assert result.decisions[0].previous_frame_sequence == 2
    with pytest.raises(StaleCountingRequestError, match="increasing"):
        _update(counter, 10)
    assert counter.statistics().stale_requests_rejected == 1


def test_empty_frame_updates_sequence_without_changing_total() -> None:
    counter = _started_counter()
    result = _update(counter, 1)

    assert result.decisions == ()
    assert result.frame_increments == 0
    assert counter.statistics().frames_without_events == 1


def test_source_lifecycle_and_crossing_fingerprint_mismatches_are_rejected() -> None:
    counter = _started_counter()
    with pytest.raises(CountingLifecycleError, match="source"):
        counter.update(crossing_result(1, source_id="other"))
    with pytest.raises(CountingLifecycleError, match="lifecycle"):
        counter.update(crossing_result(1, lifecycle_id="crossing-lifecycle-2"))
    with pytest.raises(CrossingCountingMismatchError, match="configuration"):
        counter.update(
            crossing_result(
                1,
                crossing_fingerprint="b" * 64,
            )
        )


def test_atomic_invalid_batch_does_not_apply_valid_event() -> None:
    counter = _started_counter()
    valid = crossing_event(1, 1, POSITIVE)
    mismatched = crossing_event(1, 2, POSITIVE, source_id="other")
    invalid_batch = crossing_result(1, (valid, mismatched))

    with pytest.raises(CrossingCountingMismatchError, match="does not match"):
        counter.update(invalid_batch)

    assert counter.statistics().lifecycle_directional_count == 0
    applied = _update(counter, 1, valid)
    assert applied.lifecycle_directional_count == 1


def test_counted_identity_is_not_expired_after_empty_frames() -> None:
    counter = _started_counter()
    _update(counter, 1, crossing_event(1, 1, POSITIVE))
    _update(counter, 2)
    _update(counter, 3)
    repeated = _update(counter, 4, crossing_event(4, 1, POSITIVE))

    assert repeated.decisions[0].decision_type is (CountingDecisionType.IGNORED_DUPLICATE_POSITIVE)
    assert repeated.lifecycle_directional_count == 1


def test_capacity_failure_is_atomic_and_does_not_evict_counted_identity() -> None:
    counter = _started_counter(maximum_counted_identities=1)
    _update(counter, 1, crossing_event(1, 1, POSITIVE))

    with pytest.raises(CountingCapacityError, match="not applied"):
        _update(counter, 2, crossing_event(2, 2, POSITIVE))

    assert counter.statistics().lifecycle_directional_count == 1
    duplicate = _update(counter, 2, crossing_event(2, 1, POSITIVE))
    assert duplicate.decisions[0].decision_type is (CountingDecisionType.IGNORED_DUPLICATE_POSITIVE)


def test_positive_direction_can_be_explicitly_inverted() -> None:
    counter = _started_counter(positive_direction=REVERSE)
    counted = _update(counter, 1, crossing_event(1, 1, REVERSE))
    ignored = _update(counter, 2, crossing_event(2, 2, POSITIVE))

    assert counted.frame_increments == 1
    assert ignored.decisions[0].decision_type is CountingDecisionType.IGNORED_REVERSE


def test_event_result_provenance_mismatch_is_rejected_before_mutation() -> None:
    counter = _started_counter()
    event = crossing_event(1, 1, POSITIVE)
    mismatched = replace(event, line_id="line-other")

    with pytest.raises(CrossingCountingMismatchError, match="provenance"):
        counter.update(crossing_result(1, (mismatched,)))

    assert counter.statistics().lifecycle_directional_count == 0


def test_input_type_and_duplicate_event_identity_are_rejected_by_contracts() -> None:
    counter = _started_counter()
    with pytest.raises(InputDataError, match="LiveCrossingResult"):
        counter.update(object())  # type: ignore[arg-type]

    event = crossing_event(1, 1, POSITIVE)
    with pytest.raises(InputDataError, match="at most one"):
        crossing_result(1, (event, event))


def test_crossing_fingerprint_constant_is_valid_sha256() -> None:
    assert len(CROSSING_FINGERPRINT) == 64
