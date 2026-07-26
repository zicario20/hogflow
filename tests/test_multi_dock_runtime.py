from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest
from _phase7_helpers import counting_configuration, crossing_event, crossing_result

from hogflow.counting import (
    LifecycleDirectionalCounter,
    LiveCrossingDirection,
)
from hogflow.domain import (
    DockId,
    DuplicateOperationIdError,
    InvalidOperationTransitionError,
    PigType,
    TruckOperation,
    TruckOperationStatus,
    UnloadingSession,
)
from hogflow.sessions import (
    CountingLaneOccupiedError,
    CountingLaneOwnershipError,
    DockLifecycleConflictError,
    DockOperationMismatchError,
    DockRuntimeClosedError,
    DockRuntimeNotFoundError,
    DockRuntimeOccupiedError,
    DockRuntimeStatus,
    DockSessionNotActiveError,
    DockSourceConflictError,
    MultiDockRuntimeCoordinator,
    MultiDockShutdownError,
    SessionCountingOutcome,
    SessionCountingTransferError,
    SharedCountingLane,
)

BASE = datetime(2026, 7, 25, tzinfo=timezone.utc)
SOURCE_ID = "shared_counting_lane"
POSITIVE = LiveCrossingDirection.NEGATIVE_TO_POSITIVE
REVERSE = LiveCrossingDirection.POSITIVE_TO_NEGATIVE


def at(seconds: int) -> datetime:
    return BASE + timedelta(seconds=seconds)


class CloseFailingCounter(LifecycleDirectionalCounter):
    def close(self) -> None:
        raise RuntimeError("synthetic counter close failure")


def operation(
    dock_id: DockId,
    pig_types: tuple[PigType, ...] = (PigType.REGULAR,),
    *,
    operation_id: str | None = None,
) -> TruckOperation:
    value = TruckOperation(operation_id or f"operation-{dock_id.value}", dock_id)
    for sequence, pig_type in enumerate(pig_types, start=1):
        value = value.add_session(
            UnloadingSession(
                session_id=f"{dock_id.value}-session-{sequence}",
                sequence_number=sequence,
                pig_type=pig_type,
            )
        )
    return value


def coordinator(
    counter: LifecycleDirectionalCounter | None = None,
) -> tuple[
    MultiDockRuntimeCoordinator,
    SharedCountingLane,
    LifecycleDirectionalCounter,
]:
    selected = counter or LifecycleDirectionalCounter(counting_configuration())
    lane = SharedCountingLane(selected, source_id=SOURCE_ID)
    return (
        MultiDockRuntimeCoordinator(lane, clock=lambda: at(100)),
        lane,
        selected,
    )


def register(
    runtime: MultiDockRuntimeCoordinator,
    dock_id: DockId,
    pig_types: tuple[PigType, ...] = (PigType.REGULAR,),
    *,
    operation_id: str | None = None,
) -> None:
    runtime.register_operation(
        dock_id,
        operation(dock_id, pig_types, operation_id=operation_id),
    )


def start_first_session(
    runtime: MultiDockRuntimeCoordinator,
    dock_id: DockId,
    *,
    lifecycle_id: str | None = None,
):
    runtime.start_operation(dock_id, at(0))
    return runtime.start_session(
        dock_id,
        f"{dock_id.value}-session-1",
        lifecycle_id or f"{dock_id.value}-crossing-1",
        at(1),
    )


def process(
    runtime: MultiDockRuntimeCoordinator,
    dock_id: DockId,
    frame_sequence: int,
    tracker_ids: tuple[int, ...],
    *,
    lifecycle_id: str,
    source_id: str = SOURCE_ID,
    direction: LiveCrossingDirection = POSITIVE,
    captured_at: datetime | None = None,
):
    timestamp = captured_at or at(frame_sequence + 1)
    events = tuple(
        crossing_event(
            frame_sequence,
            tracker_id,
            direction,
            source_id=source_id,
            lifecycle_id=lifecycle_id,
            captured_at=timestamp,
        )
        for tracker_id in tracker_ids
    )
    return runtime.process_counting_result(
        dock_id,
        crossing_result(
            frame_sequence,
            events,
            source_id=source_id,
            lifecycle_id=lifecycle_id,
            captured_at=timestamp,
        ),
    )


def test_registration_supports_four_operational_docks_and_one_lane() -> None:
    runtime, lane, counter = coordinator()
    pig_types = {
        DockId.DOCK_1: (PigType.REGULAR,),
        DockId.DOCK_2: (PigType.OPG, PigType.REGULAR),
        DockId.DOCK_3: (PigType.P12,),
        DockId.DOCK_4: (PigType.NAE,),
    }

    for dock_id in DockId:
        register(runtime, dock_id, pig_types[dock_id])

    snapshot = runtime.snapshot()
    assert tuple(item.dock_id for item in snapshot.dock_snapshots) == tuple(DockId)
    assert snapshot.occupied_dock_count == 4
    assert snapshot.available_dock_count == 0
    assert snapshot.active_session_count == 0
    assert snapshot.counting_lane == lane.snapshot()
    assert not counter.is_started


def test_snapshots_are_immutable_and_do_not_expose_runtime_resources() -> None:
    runtime, _lane, _counter = coordinator()
    register(runtime, DockId.DOCK_1)
    snapshot = runtime.snapshot()

    with pytest.raises(FrozenInstanceError):
        snapshot.counting_lane.current_session_count = 5  # type: ignore[misc]
    assert not hasattr(snapshot.for_dock(DockId.DOCK_1), "counter")
    assert not hasattr(snapshot.for_dock(DockId.DOCK_1), "service")
    assert not hasattr(snapshot, "registry")


def test_registration_conflicts_are_atomic() -> None:
    runtime, _lane, _counter = coordinator()
    register(runtime, DockId.DOCK_1)
    original = runtime.snapshot()

    with pytest.raises(DockRuntimeOccupiedError):
        register(runtime, DockId.DOCK_1)
    with pytest.raises(DockOperationMismatchError):
        runtime.register_operation(DockId.DOCK_2, operation(DockId.DOCK_3))
    with pytest.raises(DockSourceConflictError):
        runtime.register_operation(
            DockId.DOCK_2,
            operation(DockId.DOCK_2),
            source_id="dock_camera",
        )

    assert runtime.snapshot() == original


def test_duplicate_operation_id_is_rejected_without_lane_mutation() -> None:
    runtime, lane, _counter = coordinator()
    register(runtime, DockId.DOCK_1, operation_id="operation-shared")
    lane_before = lane.snapshot()

    with pytest.raises(DuplicateOperationIdError):
        register(runtime, DockId.DOCK_2, operation_id="operation-shared")

    assert lane.snapshot() == lane_before


def test_operation_start_is_dock_local_and_does_not_bind_lane() -> None:
    runtime, lane, counter = coordinator()
    register(runtime, DockId.DOCK_1)
    register(runtime, DockId.DOCK_2)
    dock_2_before = runtime.runtime_for(DockId.DOCK_2)

    started = runtime.start_operation(DockId.DOCK_1, at(0))

    assert started.runtime_status is DockRuntimeStatus.OPERATION_ACTIVE
    assert runtime.runtime_for(DockId.DOCK_2) == dock_2_before
    assert not lane.is_bound
    assert not counter.is_started


def test_binding_lane_to_dock_1_records_exact_ownership() -> None:
    runtime, lane, counter = coordinator()
    register(runtime, DockId.DOCK_1)

    lifecycle = start_first_session(runtime, DockId.DOCK_1)
    snapshot = runtime.snapshot()

    assert lane.is_bound
    assert counter.is_started
    assert lifecycle.source_id == SOURCE_ID
    assert snapshot.active_session_count == 1
    assert snapshot.counting_lane.active_dock_id is DockId.DOCK_1
    assert snapshot.for_dock(DockId.DOCK_1).source_id == SOURCE_ID


def test_second_dock_cannot_bind_while_shared_lane_is_busy() -> None:
    runtime, lane, _counter = coordinator()
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
        runtime.start_operation(dock_id, at(0))
    runtime.start_session(
        DockId.DOCK_1,
        "dock_1-session-1",
        "dock_1-crossing-1",
        at(1),
    )
    original = runtime.snapshot()

    with pytest.raises(CountingLaneOccupiedError, match="dock_1"):
        runtime.start_session(
            DockId.DOCK_2,
            "dock_2-session-1",
            "dock_2-crossing-1",
            at(1),
        )

    assert runtime.snapshot() == original
    assert lane.active_dock_id is DockId.DOCK_1


def test_wrong_dock_cannot_route_results_to_lane_owner() -> None:
    runtime, _lane, _counter = coordinator()
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
    start_first_session(runtime, DockId.DOCK_1)
    original = runtime.snapshot()

    with pytest.raises(CountingLaneOwnershipError):
        process(
            runtime,
            DockId.DOCK_2,
            1,
            (42,),
            lifecycle_id="dock_1-crossing-1",
        )

    assert runtime.snapshot() == original


def test_wrong_source_lifecycle_and_stale_results_are_rejected() -> None:
    runtime, _lane, _counter = coordinator()
    register(runtime, DockId.DOCK_1)
    start_first_session(runtime, DockId.DOCK_1)

    with pytest.raises(DockSourceConflictError):
        process(
            runtime,
            DockId.DOCK_1,
            1,
            (),
            lifecycle_id="dock_1-crossing-1",
            source_id="other_source",
        )
    with pytest.raises(DockLifecycleConflictError, match="another"):
        process(
            runtime,
            DockId.DOCK_1,
            1,
            (),
            lifecycle_id="other-crossing",
        )
    process(
        runtime,
        DockId.DOCK_1,
        2,
        (),
        lifecycle_id="dock_1-crossing-1",
    )
    with pytest.raises(DockLifecycleConflictError, match="stale"):
        process(
            runtime,
            DockId.DOCK_1,
            2,
            (),
            lifecycle_id="dock_1-crossing-1",
        )


def test_counts_route_only_to_bound_session() -> None:
    runtime, lane, _counter = coordinator()
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
    start_first_session(runtime, DockId.DOCK_1)

    result = process(
        runtime,
        DockId.DOCK_1,
        1,
        (1, 2),
        lifecycle_id="dock_1-crossing-1",
    )

    assert result.lifecycle_directional_count == 2
    assert lane.snapshot().current_session_count == 2
    assert runtime.runtime_for(DockId.DOCK_1).current_session_count == 2
    assert runtime.runtime_for(DockId.DOCK_2).current_session_count == 0
    assert runtime.runtime_for(DockId.DOCK_2).truck_total == 0


def test_phase_7_duplicate_and_reverse_rules_remain_authoritative() -> None:
    runtime, _lane, _counter = coordinator()
    register(runtime, DockId.DOCK_1)
    start_first_session(runtime, DockId.DOCK_1)
    first = process(
        runtime,
        DockId.DOCK_1,
        1,
        (42,),
        lifecycle_id="dock_1-crossing-1",
    )
    duplicate = process(
        runtime,
        DockId.DOCK_1,
        2,
        (42,),
        lifecycle_id="dock_1-crossing-1",
    )
    reverse = process(
        runtime,
        DockId.DOCK_1,
        3,
        (43,),
        lifecycle_id="dock_1-crossing-1",
        direction=REVERSE,
    )

    assert first.lifecycle_directional_count == 1
    assert duplicate.frame_increments == 0
    assert reverse.frame_increments == 0
    assert reverse.lifecycle_directional_count == 1


def test_complete_session_transfers_once_and_releases_lane() -> None:
    runtime, lane, counter = coordinator()
    register(runtime, DockId.DOCK_1)
    start_first_session(runtime, DockId.DOCK_1)
    process(
        runtime,
        DockId.DOCK_1,
        1,
        (1, 2),
        lifecycle_id="dock_1-crossing-1",
    )

    finalization = runtime.complete_session(DockId.DOCK_1, at(3))

    assert finalization.outcome is SessionCountingOutcome.COMPLETED
    assert finalization.finalized_count == 2
    assert runtime.runtime_for(DockId.DOCK_1).truck_total == 2
    assert not lane.is_bound
    assert not counter.is_started
    with pytest.raises(DockSessionNotActiveError):
        runtime.complete_session(DockId.DOCK_1, at(4))


def test_cancel_session_discards_live_count_and_releases_lane() -> None:
    runtime, lane, counter = coordinator()
    register(runtime, DockId.DOCK_1)
    start_first_session(runtime, DockId.DOCK_1)
    process(
        runtime,
        DockId.DOCK_1,
        1,
        (1, 2),
        lifecycle_id="dock_1-crossing-1",
    )

    finalization = runtime.cancel_session(DockId.DOCK_1, at(3))

    assert finalization.outcome is SessionCountingOutcome.CANCELLED
    assert finalization.finalized_count is None
    assert runtime.runtime_for(DockId.DOCK_1).truck_total == 0
    assert not lane.is_bound
    assert not counter.is_started


def test_next_dock_can_bind_after_prior_session_releases_lane() -> None:
    runtime, lane, _counter = coordinator()
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
        runtime.start_operation(dock_id, at(0))
    first = runtime.start_session(
        DockId.DOCK_1,
        "dock_1-session-1",
        "dock_1-crossing-1",
        at(1),
    )
    runtime.complete_session(DockId.DOCK_1, at(2))

    second = runtime.start_session(
        DockId.DOCK_2,
        "dock_2-session-1",
        "dock_2-crossing-1",
        at(3),
    )

    assert second.counting_lifecycle_id != first.counting_lifecycle_id
    assert lane.active_dock_id is DockId.DOCK_2


def test_same_tracker_id_after_new_session_is_accepted() -> None:
    runtime, _lane, _counter = coordinator()
    register(runtime, DockId.DOCK_1, (PigType.REGULAR, PigType.OPG))
    start_first_session(runtime, DockId.DOCK_1)
    first = process(
        runtime,
        DockId.DOCK_1,
        1,
        (42,),
        lifecycle_id="dock_1-crossing-1",
    )
    runtime.complete_session(DockId.DOCK_1, at(3))
    runtime.start_session(
        DockId.DOCK_1,
        "dock_1-session-2",
        "dock_1-crossing-2",
        at(4),
    )
    second = process(
        runtime,
        DockId.DOCK_1,
        1,
        (42,),
        lifecycle_id="dock_1-crossing-2",
        captured_at=at(5),
    )

    assert first.lifecycle_directional_count == 1
    assert second.lifecycle_directional_count == 1


def test_mixed_truck_uses_sequential_shared_lane_bindings() -> None:
    runtime, _lane, _counter = coordinator()
    register(
        runtime,
        DockId.DOCK_2,
        (PigType.OPG, PigType.OPG, PigType.REGULAR),
    )
    start_first_session(runtime, DockId.DOCK_2)
    for sequence, count in ((1, 2), (2, 1), (3, 2)):
        lifecycle_id = f"dock_2-crossing-{sequence}"
        if sequence > 1:
            runtime.start_session(
                DockId.DOCK_2,
                f"dock_2-session-{sequence}",
                lifecycle_id,
                at(sequence * 3 - 2),
            )
        process(
            runtime,
            DockId.DOCK_2,
            1,
            tuple(range(42, 42 + count)),
            lifecycle_id=lifecycle_id,
            captured_at=at(sequence * 3 - 1),
        )
        runtime.complete_session(DockId.DOCK_2, at(sequence * 3))

    snapshot = runtime.runtime_for(DockId.DOCK_2)
    totals = {item.pig_type: item.actual_count for item in snapshot.totals_by_pig_type}
    assert snapshot.truck_total == 5
    assert totals[PigType.OPG] == 3
    assert totals[PigType.REGULAR] == 2
    assert snapshot.finalized_lifecycle_count == 3


def test_completed_terminal_operation_leaves_lane_available() -> None:
    runtime, lane, _counter = coordinator()
    register(runtime, DockId.DOCK_3, (PigType.P12,))
    start_first_session(runtime, DockId.DOCK_3)
    process(
        runtime,
        DockId.DOCK_3,
        1,
        tuple(range(10)),
        lifecycle_id="dock_3-crossing-1",
    )
    runtime.complete_session(DockId.DOCK_3, at(3))

    terminal = runtime.complete_operation(DockId.DOCK_3, at(4))

    assert terminal.operation_status is TruckOperationStatus.COMPLETED
    assert terminal.available
    assert terminal.truck_total == 10
    assert not lane.is_bound


def test_cancel_active_operation_releases_lane_and_discards_unfinished_count() -> None:
    runtime, lane, _counter = coordinator()
    register(runtime, DockId.DOCK_4, (PigType.NAE,))
    start_first_session(runtime, DockId.DOCK_4)
    process(
        runtime,
        DockId.DOCK_4,
        1,
        (4, 5),
        lifecycle_id="dock_4-crossing-1",
    )

    cancelled = runtime.cancel_operation(DockId.DOCK_4, at(3))

    assert cancelled.operation_status is TruckOperationStatus.CANCELLED
    assert cancelled.available
    assert cancelled.truck_total == 0
    assert cancelled.finalized_lifecycle_count == 1
    assert not lane.is_bound


def test_terminal_record_replacement_has_no_count_or_lane_leakage() -> None:
    runtime, lane, _counter = coordinator()
    register(runtime, DockId.DOCK_1)
    start_first_session(runtime, DockId.DOCK_1)
    process(
        runtime,
        DockId.DOCK_1,
        1,
        (1,),
        lifecycle_id="dock_1-crossing-1",
    )
    runtime.complete_session(DockId.DOCK_1, at(3))
    runtime.complete_operation(DockId.DOCK_1, at(4))

    register(
        runtime,
        DockId.DOCK_1,
        (PigType.OPG,),
        operation_id="operation-dock_1-next",
    )
    replacement = runtime.runtime_for(DockId.DOCK_1)

    assert replacement.operation_id == "operation-dock_1-next"
    assert replacement.truck_total == 0
    assert replacement.finalized_lifecycle_count == 0
    assert not lane.is_bound


def test_finalized_crossing_lifecycle_cannot_be_reused() -> None:
    runtime, lane, _counter = coordinator()
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
        runtime.start_operation(dock_id, at(0))
    runtime.start_session(
        DockId.DOCK_1,
        "dock_1-session-1",
        "finalized-crossing",
        at(1),
    )
    runtime.complete_session(DockId.DOCK_1, at(2))

    with pytest.raises(DockLifecycleConflictError, match="finalized"):
        runtime.start_session(
            DockId.DOCK_2,
            "dock_2-session-1",
            "finalized-crossing",
            at(3),
        )

    assert not lane.is_bound


def test_snapshot_separates_live_and_finalized_totals() -> None:
    runtime, _lane, _counter = coordinator()
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
        runtime.start_operation(dock_id, at(0))
    runtime.start_session(
        DockId.DOCK_1,
        "dock_1-session-1",
        "dock_1-crossing-1",
        at(1),
    )
    process(
        runtime,
        DockId.DOCK_1,
        1,
        (1, 2),
        lifecycle_id="dock_1-crossing-1",
    )

    snapshot = runtime.snapshot()

    assert snapshot.for_dock(DockId.DOCK_1).current_session_count == 2
    assert snapshot.for_dock(DockId.DOCK_1).truck_total == 0
    assert snapshot.for_dock(DockId.DOCK_2).current_session_count == 0
    assert snapshot.aggregate_completed_pig_count == 0


def test_completed_counts_aggregate_across_docks_in_stable_pig_type_order() -> None:
    runtime, _lane, _counter = coordinator()
    for index, (dock_id, pig_type, count) in enumerate(
        (
            (DockId.DOCK_1, PigType.REGULAR, 1),
            (DockId.DOCK_2, PigType.OPG, 2),
            (DockId.DOCK_3, PigType.P12, 3),
            (DockId.DOCK_4, PigType.NAE, 4),
        ),
        start=1,
    ):
        register(runtime, dock_id, (pig_type,))
        start_first_session(runtime, dock_id, lifecycle_id=f"crossing-{index}")
        process(
            runtime,
            dock_id,
            1,
            tuple(range(count)),
            lifecycle_id=f"crossing-{index}",
        )
        runtime.complete_session(dock_id, at(index + 3))

    snapshot = runtime.snapshot()
    totals = {item.pig_type: item.actual_count for item in snapshot.aggregate_totals_by_pig_type}
    assert snapshot.aggregate_completed_pig_count == 10
    assert totals == {
        PigType.REGULAR: 1,
        PigType.OPG: 2,
        PigType.P12: 3,
        PigType.NAE: 4,
    }


def test_invalid_commands_do_not_mutate_full_snapshot() -> None:
    runtime, _lane, _counter = coordinator()
    before = runtime.snapshot()
    with pytest.raises(DockRuntimeNotFoundError):
        runtime.start_operation(DockId.DOCK_1, at(0))

    register(runtime, DockId.DOCK_1)
    planned = runtime.snapshot()
    with pytest.raises(InvalidOperationTransitionError):
        runtime.start_session(
            DockId.DOCK_1,
            "dock_1-session-1",
            "dock_1-crossing-1",
            at(1),
        )
    with pytest.raises(InvalidOperationTransitionError):
        runtime.complete_operation(DockId.DOCK_1, at(2))

    assert before.available_dock_count == 4
    assert runtime.snapshot() == planned


def test_counter_close_failure_preserves_active_session_and_lane_binding() -> None:
    counter = CloseFailingCounter(counting_configuration())
    runtime, lane, _counter = coordinator(counter)
    register(runtime, DockId.DOCK_1)
    start_first_session(runtime, DockId.DOCK_1)
    process(
        runtime,
        DockId.DOCK_1,
        1,
        (1,),
        lifecycle_id="dock_1-crossing-1",
    )
    original = runtime.snapshot()

    with pytest.raises(SessionCountingTransferError):
        runtime.complete_session(DockId.DOCK_1, at(3))

    assert runtime.snapshot() == original
    assert lane.is_bound
    assert counter.is_started


def test_close_idle_coordinator_is_idempotent() -> None:
    runtime, lane, counter = coordinator()

    first = runtime.close()
    second = runtime.close()

    assert first == second
    assert first.all_closed
    assert first.cancelled_session_dock is None
    assert runtime.is_closed
    assert lane.is_closed
    assert not counter.is_started
    with pytest.raises(DockRuntimeClosedError):
        register(runtime, DockId.DOCK_1)


def test_close_while_bound_cancels_session_and_discards_live_count() -> None:
    runtime, lane, counter = coordinator()
    register(runtime, DockId.DOCK_1)
    start_first_session(runtime, DockId.DOCK_1)
    process(
        runtime,
        DockId.DOCK_1,
        1,
        (1,),
        lifecycle_id="dock_1-crossing-1",
    )

    result = runtime.close()
    snapshot = runtime.runtime_for(DockId.DOCK_1)

    assert result.cancelled_session_dock is DockId.DOCK_1
    assert snapshot.operation_status is TruckOperationStatus.ACTIVE
    assert snapshot.active_session_id is None
    assert snapshot.truck_total == 0
    assert snapshot.finalized_lifecycle_count == 1
    assert lane.is_closed
    assert not counter.is_started


def test_shutdown_failure_keeps_coordinator_and_binding_recoverable() -> None:
    counter = CloseFailingCounter(counting_configuration())
    runtime, lane, _counter = coordinator(counter)
    register(runtime, DockId.DOCK_1)
    start_first_session(runtime, DockId.DOCK_1)
    original = runtime.snapshot()

    with pytest.raises(MultiDockShutdownError):
        runtime.close()

    assert not runtime.is_closed
    assert lane.is_bound
    assert runtime.snapshot() == original


def test_service_lifecycle_provenance_names_shared_source_and_real_dock() -> None:
    runtime, _lane, _counter = coordinator()
    register(runtime, DockId.DOCK_4, (PigType.NAE,))

    lifecycle = start_first_session(runtime, DockId.DOCK_4)

    assert lifecycle.operation_id == "operation-dock_4"
    assert lifecycle.dock_id is DockId.DOCK_4
    assert lifecycle.session_id == "dock_4-session-1"
    assert lifecycle.source_id == SOURCE_ID
    assert lifecycle.crossing_lifecycle_id == "dock_4-crossing-1"
