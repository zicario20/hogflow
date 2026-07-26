from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from _phase7_helpers import (
    counting_configuration,
    crossing_event,
    crossing_result,
)

from hogflow.counting import (
    LifecycleDirectionalCounter,
    LiveCrossingDirection,
)
from hogflow.domain import (
    DockId,
    InvalidSessionTransitionError,
    PigType,
    TruckOperation,
    UnloadingSession,
    UnloadingSessionStatus,
)
from hogflow.sessions import (
    SessionCountingConfigurationError,
    SessionCountingLifecycleError,
    SessionCountingLifecycleReuseError,
    SessionCountingOutcome,
    SessionCountingTransferError,
    UnloadingSessionCountingService,
)

BASE = datetime(2026, 7, 25, tzinfo=timezone.utc)
POSITIVE = LiveCrossingDirection.NEGATIVE_TO_POSITIVE
REVERSE = LiveCrossingDirection.POSITIVE_TO_NEGATIVE


def at(seconds: int) -> datetime:
    return BASE + timedelta(seconds=seconds)


def active_operation(
    pig_types: tuple[PigType, ...] = (PigType.REGULAR,),
    *,
    dock_id: DockId = DockId.DOCK_1,
) -> TruckOperation:
    operation = TruckOperation(f"operation-{dock_id.value}", dock_id)
    for sequence, pig_type in enumerate(pig_types, start=1):
        operation = operation.add_session(
            UnloadingSession(
                session_id=f"session-{sequence}",
                sequence_number=sequence,
                pig_type=pig_type,
            )
        )
    return operation.start(at(0))


def service_for(
    pig_types: tuple[PigType, ...] = (PigType.REGULAR,),
    *,
    dock_id: DockId = DockId.DOCK_1,
) -> tuple[UnloadingSessionCountingService, LifecycleDirectionalCounter]:
    counter = LifecycleDirectionalCounter(counting_configuration())
    service = UnloadingSessionCountingService(
        active_operation(pig_types, dock_id=dock_id),
        counter,
        source_id="camera",
    )
    return service, counter


def update(
    service: UnloadingSessionCountingService,
    frame_sequence: int,
    tracker_ids: tuple[int, ...] = (),
    *,
    lifecycle_id: str,
    captured_at: datetime,
    direction: LiveCrossingDirection = POSITIVE,
):
    events = tuple(
        crossing_event(
            frame_sequence,
            tracker_id,
            direction,
            lifecycle_id=lifecycle_id,
            captured_at=captured_at,
        )
        for tracker_id in tracker_ids
    )
    return service.update_counting(
        crossing_result(
            frame_sequence,
            events,
            lifecycle_id=lifecycle_id,
            captured_at=captured_at,
        )
    )


def test_single_session_transfers_only_validated_positive_total() -> None:
    service, counter = service_for()
    lifecycle = service.start_session("session-1", "crossing-session-1", at(1))
    first = update(
        service,
        1,
        (1, 2),
        lifecycle_id="crossing-session-1",
        captured_at=at(2),
    )
    duplicate = update(
        service,
        2,
        (1,),
        lifecycle_id="crossing-session-1",
        captured_at=at(3),
    )
    reverse = update(
        service,
        3,
        (2,),
        lifecycle_id="crossing-session-1",
        captured_at=at(4),
        direction=REVERSE,
    )
    finalization = service.complete_session(at(5))

    assert first.lifecycle_directional_count == 2
    assert duplicate.lifecycle_directional_count == reverse.lifecycle_directional_count == 2
    assert lifecycle.counting_lifecycle_id == "counting-lifecycle-1"
    assert finalization.outcome is SessionCountingOutcome.COMPLETED
    assert finalization.finalized_count == 2
    assert service.operation.session("session-1").actual_count == 2
    assert service.operation.truck_total == 2
    assert service.active_lifecycle is None
    assert not counter.is_started


def test_multiple_sequential_sessions_have_fresh_lifecycles_and_no_identity_leakage() -> None:
    service, counter = service_for((PigType.OPG, PigType.REGULAR))
    first_lifecycle = service.start_session("session-1", "crossing-session-1", at(1))
    update(
        service,
        1,
        (7,),
        lifecycle_id="crossing-session-1",
        captured_at=at(2),
    )
    first = service.complete_session(at(3))

    second_lifecycle = service.start_session("session-2", "crossing-session-2", at(4))
    assert counter.statistics().lifecycle_directional_count == 0
    assert service.current_lifecycle_count == 0
    second_result = update(
        service,
        1,
        (7,),
        lifecycle_id="crossing-session-2",
        captured_at=at(5),
    )
    second = service.complete_session(at(6))

    assert first.finalized_count == second.finalized_count == 1
    assert first_lifecycle.counting_lifecycle_id != second_lifecycle.counting_lifecycle_id
    assert second_result.frame_increments == 1
    assert service.operation.session("session-1").actual_count == 1
    assert service.operation.session("session-2").actual_count == 1
    assert service.operation.total_for(PigType.OPG) == 1
    assert service.operation.total_for(PigType.REGULAR) == 1
    assert len(service.finalized_lifecycles) == 2
    assert not counter.is_started


def test_exactly_one_lifecycle_may_own_the_active_session() -> None:
    service, counter = service_for((PigType.REGULAR, PigType.OPG))
    first = service.start_session("session-1", "crossing-session-1", at(1))
    original = service.operation

    with pytest.raises(SessionCountingLifecycleError, match="Exactly one"):
        service.start_session("session-2", "crossing-session-2", at(2))

    assert service.active_lifecycle == first
    assert service.operation == original
    assert service.operation.session("session-2").status is UnloadingSessionStatus.PLANNED
    assert counter.is_started


def test_cancel_discards_unfinished_count_and_preserves_completed_sessions() -> None:
    service, counter = service_for((PigType.OPG, PigType.REGULAR))
    service.start_session("session-1", "crossing-session-1", at(1))
    update(
        service,
        1,
        (1, 2),
        lifecycle_id="crossing-session-1",
        captured_at=at(2),
    )
    service.complete_session(at(3))

    service.start_session("session-2", "crossing-session-2", at(4))
    update(
        service,
        1,
        (3,),
        lifecycle_id="crossing-session-2",
        captured_at=at(5),
    )
    cancelled = service.cancel_session(at(6))

    assert cancelled.outcome is SessionCountingOutcome.CANCELLED
    assert cancelled.finalized_count is None
    assert service.operation.session("session-1").actual_count == 2
    assert service.operation.session("session-2").actual_count == 0
    assert service.operation.session("session-2").status is UnloadingSessionStatus.CANCELLED
    assert service.operation.truck_total == 2
    assert not counter.is_started


def test_duplicate_completion_and_finalized_count_mutation_are_rejected() -> None:
    service, _counter = service_for()
    service.start_session("session-1", "crossing-session-1", at(1))
    update(
        service,
        1,
        (1,),
        lifecycle_id="crossing-session-1",
        captured_at=at(2),
    )
    service.complete_session(at(3))

    with pytest.raises(SessionCountingLifecycleError, match="No unloading session"):
        service.complete_session(at(4))
    with pytest.raises(InvalidSessionTransitionError, match="active session"):
        service.operation.complete_session("session-1", 99, at(4))
    assert service.operation.session("session-1").actual_count == 1


def test_finalized_crossing_lifecycle_cannot_be_reused() -> None:
    service, counter = service_for((PigType.REGULAR, PigType.REGULAR))
    service.start_session("session-1", "crossing-shared", at(1))
    service.complete_session(at(2))
    original = service.operation

    with pytest.raises(SessionCountingLifecycleReuseError, match="cannot be assigned"):
        service.start_session("session-2", "crossing-shared", at(3))

    assert service.operation == original
    assert service.operation.session("session-2").status is UnloadingSessionStatus.PLANNED
    assert not counter.is_started


def test_lifecycle_validator_rejection_closes_counter_without_committing_session() -> None:
    service, counter = service_for()
    original = service.operation

    def reject(_lifecycle) -> None:
        raise SessionCountingLifecycleError("synthetic global lifecycle conflict")

    with pytest.raises(SessionCountingLifecycleError, match="global lifecycle conflict"):
        service.start_session(
            "session-1",
            "crossing-session-1",
            at(1),
            lifecycle_validator=reject,
        )

    assert service.operation == original
    assert service.active_lifecycle is None
    assert service.finalized_lifecycles == ()
    assert not counter.is_started


def test_crossing_source_lifecycle_and_time_are_validated_before_counting() -> None:
    service, counter = service_for()
    lifecycle = service.start_session("session-1", "crossing-session-1", at(2))

    with pytest.raises(SessionCountingLifecycleError, match="active session lifecycle"):
        service.update_counting(
            crossing_result(
                1,
                source_id="other",
                lifecycle_id="crossing-session-1",
                captured_at=at(3),
            )
        )
    with pytest.raises(SessionCountingLifecycleError, match="precede"):
        service.update_counting(
            crossing_result(
                1,
                lifecycle_id="crossing-session-1",
                captured_at=at(1),
            )
        )

    assert service.active_lifecycle == lifecycle
    assert counter.statistics().crossing_results_processed == 0


def test_completion_and_cancellation_cannot_precede_latest_counting_result() -> None:
    service, counter = service_for()
    service.start_session("session-1", "crossing-session-1", at(1))
    update(
        service,
        1,
        (1,),
        lifecycle_id="crossing-session-1",
        captured_at=at(4),
    )
    original = service.operation

    with pytest.raises(SessionCountingTransferError, match="latest counting result"):
        service.complete_session(at(3))

    assert service.operation == original
    assert service.active_lifecycle is not None
    assert counter.is_started


def test_service_rejects_unsafe_initial_state() -> None:
    planned = TruckOperation("operation-1", DockId.DOCK_1).add_session(
        UnloadingSession("session-1", 1, PigType.REGULAR)
    )
    counter = LifecycleDirectionalCounter(counting_configuration())

    with pytest.raises(SessionCountingConfigurationError, match="active truck"):
        UnloadingSessionCountingService(planned, counter, source_id="camera")

    active_session = planned.start(at(0)).start_session("session-1", at(1))
    with pytest.raises(SessionCountingConfigurationError, match="existing active"):
        UnloadingSessionCountingService(active_session, counter, source_id="camera")


class CloseFailingCounter:
    def __init__(self) -> None:
        self.delegate = LifecycleDirectionalCounter(counting_configuration())

    @property
    def configuration(self):
        return self.delegate.configuration

    @property
    def is_started(self) -> bool:
        return self.delegate.is_started

    @property
    def source_id(self) -> str:
        return self.delegate.source_id

    @property
    def crossing_lifecycle_id(self) -> str:
        return self.delegate.crossing_lifecycle_id

    @property
    def counting_lifecycle_id(self) -> str:
        return self.delegate.counting_lifecycle_id

    def start(self, source_id: str, crossing_lifecycle_id: str) -> None:
        self.delegate.start(source_id, crossing_lifecycle_id)

    def update(self, crossing):
        return self.delegate.update(crossing)

    def reset(self, crossing_lifecycle_id: str) -> None:
        self.delegate.reset(crossing_lifecycle_id)

    def close(self) -> None:
        raise RuntimeError("synthetic close failure")

    def statistics(self):
        return self.delegate.statistics()

    def record_preview_failure(self) -> None:
        self.delegate.record_preview_failure()


def test_failed_counter_close_does_not_transfer_or_partially_complete_session() -> None:
    counter = CloseFailingCounter()
    service = UnloadingSessionCountingService(
        active_operation(),
        counter,
        source_id="camera",
    )
    service.start_session("session-1", "crossing-session-1", at(1))
    update(
        service,
        1,
        (1,),
        lifecycle_id="crossing-session-1",
        captured_at=at(2),
    )
    original = service.operation

    with pytest.raises(SessionCountingTransferError, match="not transferred"):
        service.complete_session(at(3))

    assert service.operation == original
    assert service.operation.session("session-1").status is UnloadingSessionStatus.ACTIVE
    assert service.operation.session("session-1").actual_count == 0
    assert service.finalized_lifecycles == ()
