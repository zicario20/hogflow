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
    DockLifecycleConflictError,
    DockOperationMismatchError,
    DockRuntimeClosedError,
    DockRuntimeConfigurationError,
    DockRuntimeNotFoundError,
    DockRuntimeOccupiedError,
    DockRuntimeStatus,
    DockRuntimeTransitionError,
    DockSessionNotActiveError,
    DockSourceConflictError,
    MultiDockRuntimeCoordinator,
    MultiDockShutdownError,
    SessionCountingOutcome,
    SessionCountingTransferError,
)

BASE = datetime(2026, 7, 25, tzinfo=timezone.utc)
POSITIVE = LiveCrossingDirection.NEGATIVE_TO_POSITIVE
REVERSE = LiveCrossingDirection.POSITIVE_TO_NEGATIVE


def at(seconds: int) -> datetime:
    return BASE + timedelta(seconds=seconds)


class NamespacedCounter(LifecycleDirectionalCounter):
    def __init__(self, namespace: str) -> None:
        super().__init__(counting_configuration())
        self.namespace = namespace

    @property
    def counting_lifecycle_id(self) -> str:
        return f"{self.namespace}-{super().counting_lifecycle_id}"


class FixedLifecycleCounter(LifecycleDirectionalCounter):
    @property
    def counting_lifecycle_id(self) -> str:
        if not self.is_started:
            return super().counting_lifecycle_id
        return "shared-counting-lifecycle"


class CloseFailingCounter(NamespacedCounter):
    def close(self) -> None:
        raise RuntimeError("synthetic counter close failure")


class CounterFactory:
    def __init__(
        self,
        *,
        fixed_lifecycle: bool = False,
        fail_for: DockId | None = None,
        fail_close_for: DockId | None = None,
    ) -> None:
        self.fixed_lifecycle = fixed_lifecycle
        self.fail_for = fail_for
        self.fail_close_for = fail_close_for
        self.counters: dict[DockId, LifecycleDirectionalCounter] = {}

    def __call__(self, dock_id: DockId, source_id: str):
        del source_id
        if dock_id is self.fail_for:
            raise RuntimeError("synthetic factory failure")
        if dock_id is self.fail_close_for:
            counter = CloseFailingCounter(dock_id.value)
        elif self.fixed_lifecycle:
            counter = FixedLifecycleCounter(counting_configuration())
        else:
            counter = NamespacedCounter(dock_id.value)
        self.counters[dock_id] = counter
        return counter


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
    factory: CounterFactory | None = None,
) -> tuple[MultiDockRuntimeCoordinator, CounterFactory]:
    selected = factory or CounterFactory()
    return MultiDockRuntimeCoordinator(selected, clock=lambda: at(100)), selected


def register(
    runtime: MultiDockRuntimeCoordinator,
    dock_id: DockId,
    pig_types: tuple[PigType, ...] = (PigType.REGULAR,),
    *,
    source_id: str | None = None,
    operation_id: str | None = None,
) -> None:
    runtime.register_operation(
        dock_id,
        operation(dock_id, pig_types, operation_id=operation_id),
        source_id=source_id or f"{dock_id.value}_camera",
    )


def start_first_session(
    runtime: MultiDockRuntimeCoordinator,
    dock_id: DockId,
    *,
    lifecycle_id: str | None = None,
    started_at: datetime | None = None,
):
    runtime.start_operation(dock_id, at(0))
    return runtime.start_session(
        dock_id,
        f"{dock_id.value}-session-1",
        lifecycle_id or f"{dock_id.value}-crossing-1",
        started_at or at(1),
    )


def process(
    runtime: MultiDockRuntimeCoordinator,
    dock_id: DockId,
    frame_sequence: int,
    tracker_ids: tuple[int, ...],
    *,
    lifecycle_id: str | None = None,
    source_id: str | None = None,
    direction: LiveCrossingDirection = POSITIVE,
    captured_at: datetime | None = None,
):
    lifecycle = lifecycle_id or f"{dock_id.value}-crossing-1"
    source = source_id or f"{dock_id.value}_camera"
    timestamp = captured_at or at(frame_sequence + 1)
    events = tuple(
        crossing_event(
            frame_sequence,
            tracker_id,
            direction,
            source_id=source,
            lifecycle_id=lifecycle,
            captured_at=timestamp,
        )
        for tracker_id in tracker_ids
    )
    return runtime.process_counting_result(
        dock_id,
        crossing_result(
            frame_sequence,
            events,
            source_id=source,
            lifecycle_id=lifecycle,
            captured_at=timestamp,
        ),
    )


def test_registration_supports_all_four_docks_in_deterministic_order() -> None:
    runtime, factory = coordinator()
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
    assert all(item.runtime_status is DockRuntimeStatus.PLANNED for item in snapshot.dock_snapshots)
    assert set(factory.counters) == set(DockId)


def test_runtime_snapshots_are_immutable_and_do_not_expose_owned_resources() -> None:
    runtime, _factory = coordinator()
    register(runtime, DockId.DOCK_1)
    snapshot = runtime.snapshot()
    dock_snapshot = snapshot.for_dock(DockId.DOCK_1)

    with pytest.raises(FrozenInstanceError):
        dock_snapshot.current_session_count = 5  # type: ignore[misc]
    assert not hasattr(dock_snapshot, "counter")
    assert not hasattr(dock_snapshot, "service")
    assert not hasattr(snapshot, "registry")


def test_registration_rejects_invalid_ownership_conflicts_atomically() -> None:
    runtime, factory = coordinator()
    register(runtime, DockId.DOCK_1, source_id="shared_camera")
    original = runtime.snapshot()

    with pytest.raises(DockRuntimeOccupiedError, match="non-terminal"):
        register(runtime, DockId.DOCK_1)
    with pytest.raises(DockOperationMismatchError, match="another dock"):
        runtime.register_operation(
            DockId.DOCK_2,
            operation(DockId.DOCK_3),
            source_id="dock_2_camera",
        )
    with pytest.raises(DockSourceConflictError, match="another active dock"):
        register(runtime, DockId.DOCK_2, source_id="shared_camera")
    with pytest.raises(DockRuntimeNotFoundError, match="supported dock"):
        runtime.runtime_for("dock_5")  # type: ignore[arg-type]

    assert runtime.snapshot() == original
    assert set(factory.counters) == {DockId.DOCK_1}


def test_counter_factory_failure_leaves_every_dock_unchanged() -> None:
    runtime, _factory = coordinator(CounterFactory(fail_for=DockId.DOCK_2))
    register(runtime, DockId.DOCK_1)
    original = runtime.snapshot()

    with pytest.raises(DockRuntimeConfigurationError, match="factory failed"):
        register(runtime, DockId.DOCK_2)

    assert runtime.snapshot() == original
    assert runtime.runtime_for(DockId.DOCK_2).runtime_status is DockRuntimeStatus.AVAILABLE


def test_duplicate_operation_id_is_rejected_before_counter_creation() -> None:
    runtime, factory = coordinator()
    register(runtime, DockId.DOCK_1, operation_id="operation-shared")
    original = runtime.snapshot()

    with pytest.raises(DuplicateOperationIdError):
        register(runtime, DockId.DOCK_2, operation_id="operation-shared")

    assert runtime.snapshot() == original
    assert set(factory.counters) == {DockId.DOCK_1}


def test_operation_start_is_dock_local_and_does_not_start_counter() -> None:
    runtime, factory = coordinator()
    register(runtime, DockId.DOCK_1)
    register(runtime, DockId.DOCK_2)
    dock_2_before = runtime.runtime_for(DockId.DOCK_2)

    started = runtime.start_operation(DockId.DOCK_1, at(0))

    assert started.runtime_status is DockRuntimeStatus.OPERATION_ACTIVE
    assert not factory.counters[DockId.DOCK_1].is_started
    assert runtime.runtime_for(DockId.DOCK_2) == dock_2_before


def test_four_sessions_can_remain_logically_active_with_isolated_lifecycles() -> None:
    runtime, factory = coordinator()
    for dock_id in DockId:
        register(runtime, dock_id)
        lifecycle = start_first_session(runtime, dock_id)
        assert lifecycle.source_id == f"{dock_id.value}_camera"
        assert lifecycle.crossing_lifecycle_id == f"{dock_id.value}-crossing-1"
        assert lifecycle.counting_lifecycle_id.startswith(dock_id.value)

    snapshot = runtime.snapshot()
    assert snapshot.active_session_count == 4
    assert len({item.counting_lifecycle_id for item in snapshot.dock_snapshots}) == 4
    assert all(factory.counters[dock_id].is_started for dock_id in DockId)


def test_same_tracker_identity_counts_independently_across_docks() -> None:
    runtime, _factory = coordinator()
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
        start_first_session(runtime, dock_id)

    dock_1_result = process(runtime, DockId.DOCK_1, 1, (42,))
    dock_2_result = process(runtime, DockId.DOCK_2, 1, (42,))

    assert dock_1_result.lifecycle_directional_count == 1
    assert dock_2_result.lifecycle_directional_count == 1
    assert runtime.runtime_for(DockId.DOCK_1).current_session_count == 1
    assert runtime.runtime_for(DockId.DOCK_2).current_session_count == 1


def test_duplicate_identity_is_suppressed_only_inside_its_dock_session() -> None:
    runtime, _factory = coordinator()
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
        start_first_session(runtime, dock_id)

    process(runtime, DockId.DOCK_1, 1, (42,))
    duplicate = process(runtime, DockId.DOCK_1, 2, (42,))

    assert duplicate.frame_increments == 0
    assert duplicate.lifecycle_directional_count == 1
    assert runtime.runtime_for(DockId.DOCK_2).current_session_count == 0


def test_wrong_source_lifecycle_and_stale_frames_are_rejected_locally() -> None:
    runtime, _factory = coordinator()
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
        start_first_session(runtime, dock_id)
    process(runtime, DockId.DOCK_2, 1, (8,))
    dock_2_before = runtime.runtime_for(DockId.DOCK_2)

    with pytest.raises(DockSourceConflictError, match="another source"):
        process(
            runtime,
            DockId.DOCK_1,
            1,
            (),
            source_id="dock_2_camera",
        )
    with pytest.raises(DockLifecycleConflictError, match="another lifecycle"):
        process(
            runtime,
            DockId.DOCK_1,
            1,
            (),
            lifecycle_id="wrong-crossing",
        )
    process(runtime, DockId.DOCK_1, 2, ())
    with pytest.raises(DockLifecycleConflictError, match="stale"):
        process(runtime, DockId.DOCK_1, 2, ())

    assert runtime.runtime_for(DockId.DOCK_2) == dock_2_before


def test_crossing_lifecycle_collision_is_rejected_before_second_counter_starts() -> None:
    runtime, factory = coordinator()
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
        runtime.start_operation(dock_id, at(0))
    runtime.start_session(
        DockId.DOCK_1,
        "dock_1-session-1",
        "shared-crossing",
        at(1),
    )
    dock_1_before = runtime.runtime_for(DockId.DOCK_1)

    with pytest.raises(DockLifecycleConflictError, match="another active dock"):
        runtime.start_session(
            DockId.DOCK_2,
            "dock_2-session-1",
            "shared-crossing",
            at(1),
        )

    assert runtime.runtime_for(DockId.DOCK_1) == dock_1_before
    assert runtime.runtime_for(DockId.DOCK_2).active_session_id is None
    assert not factory.counters[DockId.DOCK_2].is_started


def test_counting_lifecycle_collision_rolls_back_prospective_session_start() -> None:
    runtime, factory = coordinator(CounterFactory(fixed_lifecycle=True))
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
        runtime.start_operation(dock_id, at(0))
    runtime.start_session(
        DockId.DOCK_1,
        "dock_1-session-1",
        "dock_1-crossing-1",
        at(1),
    )
    dock_2_before = runtime.runtime_for(DockId.DOCK_2)

    with pytest.raises(DockLifecycleConflictError, match="Counting lifecycle"):
        runtime.start_session(
            DockId.DOCK_2,
            "dock_2-session-1",
            "dock_2-crossing-1",
            at(1),
        )

    assert runtime.runtime_for(DockId.DOCK_2) == dock_2_before
    assert not factory.counters[DockId.DOCK_2].is_started
    assert factory.counters[DockId.DOCK_1].is_started


def test_completed_session_transfers_once_and_preserves_other_docks() -> None:
    runtime, _factory = coordinator()
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
        start_first_session(runtime, dock_id)
    process(runtime, DockId.DOCK_1, 1, (1, 2))
    dock_2_before = runtime.runtime_for(DockId.DOCK_2)

    finalization = runtime.complete_session(DockId.DOCK_1, at(3))

    assert finalization.outcome is SessionCountingOutcome.COMPLETED
    assert finalization.finalized_count == 2
    assert runtime.runtime_for(DockId.DOCK_1).truck_total == 2
    assert runtime.runtime_for(DockId.DOCK_1).current_session_count == 0
    assert runtime.runtime_for(DockId.DOCK_2) == dock_2_before
    with pytest.raises(DockSessionNotActiveError):
        runtime.complete_session(DockId.DOCK_1, at(4))


def test_mixed_truck_sequential_sessions_use_fresh_identity_scopes() -> None:
    runtime, _factory = coordinator()
    register(
        runtime,
        DockId.DOCK_2,
        (PigType.OPG, PigType.OPG, PigType.REGULAR),
    )
    start_first_session(runtime, DockId.DOCK_2)
    process(runtime, DockId.DOCK_2, 1, (42, 43))
    runtime.complete_session(DockId.DOCK_2, at(3))

    for sequence, pig_type_count in ((2, 1), (3, 2)):
        lifecycle = f"dock_2-crossing-{sequence}"
        runtime.start_session(
            DockId.DOCK_2,
            f"dock_2-session-{sequence}",
            lifecycle,
            at(sequence * 3 - 2),
        )
        process(
            runtime,
            DockId.DOCK_2,
            1,
            tuple(range(42, 42 + pig_type_count)),
            lifecycle_id=lifecycle,
            captured_at=at(sequence * 3 - 1),
        )
        runtime.complete_session(DockId.DOCK_2, at(sequence * 3))

    snapshot = runtime.runtime_for(DockId.DOCK_2)
    totals = {item.pig_type: item.actual_count for item in snapshot.totals_by_pig_type}
    assert snapshot.truck_total == 5
    assert totals[PigType.OPG] == 3
    assert totals[PigType.REGULAR] == 2
    assert snapshot.finalized_lifecycle_count == 3


def test_cancel_session_discards_live_count_and_keeps_prior_finalized_total() -> None:
    runtime, _factory = coordinator()
    register(runtime, DockId.DOCK_1, (PigType.REGULAR, PigType.REGULAR))
    start_first_session(runtime, DockId.DOCK_1)
    process(runtime, DockId.DOCK_1, 1, (1,))
    runtime.complete_session(DockId.DOCK_1, at(3))
    runtime.start_session(
        DockId.DOCK_1,
        "dock_1-session-2",
        "dock_1-crossing-2",
        at(4),
    )
    process(
        runtime,
        DockId.DOCK_1,
        1,
        (2, 3),
        lifecycle_id="dock_1-crossing-2",
        captured_at=at(5),
    )

    finalization = runtime.cancel_session(DockId.DOCK_1, at(6))

    assert finalization.outcome is SessionCountingOutcome.CANCELLED
    assert finalization.finalized_count is None
    assert runtime.runtime_for(DockId.DOCK_1).truck_total == 1


def test_cancel_active_truck_discards_unfinished_count_and_releases_only_its_dock() -> None:
    runtime, factory = coordinator()
    for dock_id in (DockId.DOCK_1, DockId.DOCK_4):
        register(runtime, dock_id, (PigType.NAE,))
        start_first_session(runtime, dock_id)
    process(runtime, DockId.DOCK_4, 1, (4, 5))
    dock_1_before = runtime.runtime_for(DockId.DOCK_1)

    cancelled = runtime.cancel_operation(DockId.DOCK_4, at(3))

    assert cancelled.operation_status is TruckOperationStatus.CANCELLED
    assert cancelled.available
    assert cancelled.truck_total == 0
    assert cancelled.finalized_lifecycle_count == 1
    assert not factory.counters[DockId.DOCK_4].is_started
    assert runtime.runtime_for(DockId.DOCK_1) == dock_1_before


def test_complete_small_load_releases_dock_and_keeps_terminal_snapshot() -> None:
    runtime, _factory = coordinator()
    register(runtime, DockId.DOCK_3, (PigType.P12,))
    start_first_session(runtime, DockId.DOCK_3)
    process(runtime, DockId.DOCK_3, 1, tuple(range(10)))
    runtime.complete_session(DockId.DOCK_3, at(3))

    terminal = runtime.complete_operation(DockId.DOCK_3, at(4))

    assert terminal.runtime_status is DockRuntimeStatus.TERMINAL
    assert terminal.operation_status is TruckOperationStatus.COMPLETED
    assert terminal.available
    assert terminal.truck_total == 10
    assert terminal.active_session_id is None


def test_terminal_record_can_be_replaced_without_state_leakage() -> None:
    runtime, factory = coordinator()
    register(runtime, DockId.DOCK_1)
    start_first_session(runtime, DockId.DOCK_1)
    process(runtime, DockId.DOCK_1, 1, (1,))
    runtime.complete_session(DockId.DOCK_1, at(3))
    runtime.complete_operation(DockId.DOCK_1, at(4))
    old_counter = factory.counters[DockId.DOCK_1]

    register(
        runtime,
        DockId.DOCK_1,
        (PigType.OPG,),
        source_id="dock_1_new_camera",
        operation_id="operation-dock_1-next",
    )
    replacement = runtime.runtime_for(DockId.DOCK_1)

    assert replacement.operation_id == "operation-dock_1-next"
    assert replacement.runtime_status is DockRuntimeStatus.PLANNED
    assert replacement.truck_total == 0
    assert replacement.finalized_lifecycle_count == 0
    assert replacement.source_id == "dock_1_new_camera"
    assert factory.counters[DockId.DOCK_1] is not old_counter

    runtime.start_operation(DockId.DOCK_1, at(5))
    runtime.start_session(
        DockId.DOCK_1,
        "dock_1-session-1",
        "dock_1-new-crossing",
        at(6),
    )
    fresh = process(
        runtime,
        DockId.DOCK_1,
        1,
        (1,),
        lifecycle_id="dock_1-new-crossing",
        source_id="dock_1_new_camera",
        captured_at=at(7),
    )
    assert fresh.lifecycle_directional_count == 1


def test_finalized_lifecycle_reuse_is_rejected_across_current_docks() -> None:
    runtime, factory = coordinator()
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
        runtime.start_operation(dock_id, at(0))
    lifecycle = runtime.start_session(
        DockId.DOCK_1,
        "dock_1-session-1",
        "finalized-crossing",
        at(1),
    )
    runtime.complete_session(DockId.DOCK_1, at(2))
    runtime.complete_operation(DockId.DOCK_1, at(3))

    with pytest.raises(DockLifecycleConflictError, match="finalized crossing"):
        runtime.start_session(
            DockId.DOCK_2,
            "dock_2-session-1",
            "finalized-crossing",
            at(4),
        )

    assert not factory.counters[DockId.DOCK_2].is_started
    assert lifecycle.counting_lifecycle_id.startswith("dock_1")


def test_finalized_counting_lifecycle_reuse_is_rejected_across_current_docks() -> None:
    runtime, factory = coordinator(CounterFactory(fixed_lifecycle=True))
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
        runtime.start_operation(dock_id, at(0))
    runtime.start_session(
        DockId.DOCK_1,
        "dock_1-session-1",
        "dock_1-crossing-1",
        at(1),
    )
    runtime.complete_session(DockId.DOCK_1, at(2))
    runtime.complete_operation(DockId.DOCK_1, at(3))

    with pytest.raises(DockLifecycleConflictError, match="finalized counting"):
        runtime.start_session(
            DockId.DOCK_2,
            "dock_2-session-1",
            "dock_2-crossing-1",
            at(4),
        )

    assert not factory.counters[DockId.DOCK_2].is_started
    assert runtime.runtime_for(DockId.DOCK_2).active_session_id is None


def test_cancel_active_truck_preserves_earlier_completed_session_total() -> None:
    runtime, _factory = coordinator()
    register(runtime, DockId.DOCK_4, (PigType.NAE, PigType.NAE))
    start_first_session(runtime, DockId.DOCK_4)
    process(runtime, DockId.DOCK_4, 1, (1, 2))
    runtime.complete_session(DockId.DOCK_4, at(3))
    runtime.start_session(
        DockId.DOCK_4,
        "dock_4-session-2",
        "dock_4-crossing-2",
        at(4),
    )
    process(
        runtime,
        DockId.DOCK_4,
        1,
        (3, 4, 5),
        lifecycle_id="dock_4-crossing-2",
        captured_at=at(5),
    )

    cancelled = runtime.cancel_operation(DockId.DOCK_4, at(6))

    assert cancelled.operation_status is TruckOperationStatus.CANCELLED
    assert cancelled.truck_total == 2
    assert cancelled.current_session_count == 0
    assert cancelled.finalized_lifecycle_count == 2
    assert cancelled.totals_by_pig_type[-1].actual_count == 2


def test_snapshot_separates_live_counts_from_finalized_aggregate_totals() -> None:
    runtime, _factory = coordinator()
    for dock_id in (DockId.DOCK_1, DockId.DOCK_2):
        register(runtime, dock_id)
        start_first_session(runtime, dock_id)
    process(runtime, DockId.DOCK_1, 1, (1, 2))
    process(runtime, DockId.DOCK_2, 1, (3,))
    runtime.complete_session(DockId.DOCK_1, at(3))

    snapshot = runtime.snapshot()

    assert snapshot.for_dock(DockId.DOCK_1).truck_total == 2
    assert snapshot.for_dock(DockId.DOCK_2).current_session_count == 1
    assert snapshot.for_dock(DockId.DOCK_2).truck_total == 0
    assert snapshot.aggregate_completed_pig_count == 2
    assert snapshot.aggregate_totals_by_pig_type[0].actual_count == 2
    assert snapshot.generated_at == at(100)


def test_combined_totals_cover_all_pig_types_without_live_count_inflation() -> None:
    runtime, _factory = coordinator()
    for dock_id, pig_type, count in (
        (DockId.DOCK_1, PigType.REGULAR, 1),
        (DockId.DOCK_2, PigType.OPG, 2),
        (DockId.DOCK_3, PigType.P12, 3),
        (DockId.DOCK_4, PigType.NAE, 4),
    ):
        register(runtime, dock_id, (pig_type,))
        start_first_session(runtime, dock_id)
        process(runtime, dock_id, 1, tuple(range(count)))
        if dock_id is not DockId.DOCK_4:
            runtime.complete_session(dock_id, at(3))

    snapshot = runtime.snapshot()
    totals = {item.pig_type: item.actual_count for item in snapshot.aggregate_totals_by_pig_type}
    assert snapshot.aggregate_completed_pig_count == 6
    assert totals == {
        PigType.REGULAR: 1,
        PigType.OPG: 2,
        PigType.P12: 3,
        PigType.NAE: 0,
    }
    assert snapshot.for_dock(DockId.DOCK_4).current_session_count == 4


def test_commands_requiring_active_runtime_fail_without_mutation() -> None:
    runtime, _factory = coordinator()
    before = runtime.snapshot()

    with pytest.raises(DockRuntimeNotFoundError):
        runtime.start_operation(DockId.DOCK_1, at(0))

    register(runtime, DockId.DOCK_1)
    planned = runtime.snapshot()
    with pytest.raises(DockRuntimeTransitionError, match="has not started"):
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


def test_failed_counter_close_does_not_commit_operation_completion() -> None:
    runtime, _factory = coordinator(CounterFactory(fail_close_for=DockId.DOCK_1))
    register(runtime, DockId.DOCK_1)
    start_first_session(runtime, DockId.DOCK_1)
    process(runtime, DockId.DOCK_1, 1, (1,))

    with pytest.raises(SessionCountingTransferError):
        runtime.cancel_session(DockId.DOCK_1, at(3))

    snapshot = runtime.runtime_for(DockId.DOCK_1)
    assert snapshot.operation_status is TruckOperationStatus.ACTIVE
    assert snapshot.active_session_id == "dock_1-session-1"
    assert snapshot.current_session_count == 1


def test_close_empty_and_repeated_close_are_idempotent() -> None:
    runtime, _factory = coordinator()

    first = runtime.close()
    second = runtime.close()

    assert first == second
    assert first.all_closed
    assert first.closed_docks == ()
    assert runtime.is_closed
    assert runtime.snapshot().coordinator_closed
    with pytest.raises(DockRuntimeClosedError):
        register(runtime, DockId.DOCK_1)


def test_close_active_sessions_cancels_them_without_fabricating_truck_completion() -> None:
    runtime, factory = coordinator()
    register(runtime, DockId.DOCK_1)
    start_first_session(runtime, DockId.DOCK_1)
    process(runtime, DockId.DOCK_1, 1, (1,))

    result = runtime.close()
    snapshot = runtime.runtime_for(DockId.DOCK_1)

    assert result.active_session_docks == (DockId.DOCK_1,)
    assert result.closed_docks == (DockId.DOCK_1,)
    assert snapshot.operation_status is TruckOperationStatus.ACTIVE
    assert snapshot.active_session_id is None
    assert snapshot.current_session_count == 0
    assert snapshot.truck_total == 0
    assert snapshot.finalized_lifecycle_count == 1
    assert not factory.counters[DockId.DOCK_1].is_started


def test_partial_shutdown_attempts_all_docks_and_reports_failures() -> None:
    runtime, factory = coordinator(CounterFactory(fail_close_for=DockId.DOCK_1))
    register(runtime, DockId.DOCK_1)
    register(runtime, DockId.DOCK_2)

    with pytest.raises(MultiDockShutdownError) as captured:
        runtime.close()

    assert captured.value.failed_dock_values == ("dock_1",)
    assert captured.value.closed_dock_values == ("dock_2",)
    assert runtime.is_closed
    assert not factory.counters[DockId.DOCK_2].is_started
    with pytest.raises(MultiDockShutdownError):
        runtime.close()


def test_reverse_event_remains_phase_7_zero_increment_behavior() -> None:
    runtime, _factory = coordinator()
    register(runtime, DockId.DOCK_1)
    start_first_session(runtime, DockId.DOCK_1)

    result = process(runtime, DockId.DOCK_1, 1, (1,), direction=REVERSE)

    assert result.frame_increments == 0
    assert result.lifecycle_directional_count == 0
    assert runtime.runtime_for(DockId.DOCK_1).current_session_count == 0


def test_service_lifecycle_provenance_remains_exact_at_runtime_boundary() -> None:
    runtime, _factory = coordinator()
    register(runtime, DockId.DOCK_4, (PigType.NAE,))
    lifecycle = start_first_session(runtime, DockId.DOCK_4)

    assert lifecycle.operation_id == "operation-dock_4"
    assert lifecycle.dock_id is DockId.DOCK_4
    assert lifecycle.session_id == "dock_4-session-1"
    assert lifecycle.source_id == "dock_4_camera"
    assert lifecycle.crossing_lifecycle_id == "dock_4-crossing-1"
    assert lifecycle.counting_lifecycle_id.startswith("dock_4")
