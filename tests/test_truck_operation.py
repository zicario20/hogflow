from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from hogflow.domain import (
    DockId,
    DuplicateSessionIdError,
    DuplicateSessionSequenceError,
    InvalidCountError,
    InvalidOperationTransitionError,
    InvalidSessionTransitionError,
    PigType,
    TruckOperation,
    TruckOperationStatus,
    UnloadingSession,
    UnloadingSessionStatus,
)

BASE = datetime(2026, 7, 25, 8, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return BASE + timedelta(minutes=minutes)


def planned_operation(
    dock_id: DockId = DockId.DOCK_1,
    pig_types: tuple[PigType, ...] = (PigType.REGULAR,),
) -> TruckOperation:
    operation = TruckOperation(f"operation-{dock_id.value}", dock_id)
    for sequence, pig_type in enumerate(pig_types, start=1):
        operation = operation.add_session(
            UnloadingSession(
                session_id=f"session-{sequence}",
                sequence_number=sequence,
                pig_type=pig_type,
                expected_count=60,
            )
        )
    return operation


def complete_operation(
    operation: TruckOperation,
    counts: tuple[int, ...],
) -> TruckOperation:
    operation = operation.start(at(0))
    minute = 1
    for session, count in zip(operation.sessions, counts):
        operation = operation.start_session(session.session_id, at(minute))
        minute += 1
        operation = operation.complete_session(session.session_id, count, at(minute))
        minute += 1
    return operation.complete(at(minute))


@pytest.mark.parametrize("session_count", (1, 2, 3, 4, 6))
def test_operation_supports_variable_session_quantities(session_count: int) -> None:
    operation = planned_operation(pig_types=tuple(PigType.REGULAR for _ in range(session_count)))
    assert len(operation.sessions) == session_count


def test_sessions_are_canonicalized_in_sequence_order() -> None:
    operation = TruckOperation(
        operation_id="operation-1",
        dock_id=DockId.DOCK_1,
        sessions=(
            UnloadingSession("session-3", 3, PigType.REGULAR),
            UnloadingSession("session-1", 1, PigType.REGULAR),
            UnloadingSession("session-2", 2, PigType.REGULAR),
        ),
    )
    assert tuple(session.sequence_number for session in operation.sessions) == (1, 2, 3)


def test_duplicate_session_sequence_is_atomic() -> None:
    original = planned_operation()
    with pytest.raises(DuplicateSessionSequenceError, match="sequence number"):
        original.add_session(UnloadingSession("session-other", 1, PigType.OPG))
    assert len(original.sessions) == 1
    assert original.sessions[0].pig_type is PigType.REGULAR


def test_duplicate_session_id_is_atomic() -> None:
    original = planned_operation()
    with pytest.raises(DuplicateSessionIdError, match="Session ID"):
        original.add_session(UnloadingSession("session-1", 2, PigType.OPG))
    assert len(original.sessions) == 1


def test_operation_cannot_activate_without_sessions() -> None:
    operation = TruckOperation("operation-1", DockId.DOCK_1)
    with pytest.raises(InvalidOperationTransitionError, match="at least one session"):
        operation.start(at(0))
    assert operation.status is TruckOperationStatus.PLANNED
    assert operation.started_at is None


def test_direct_completed_operation_requires_a_start_timestamp() -> None:
    completed_session = (
        UnloadingSession("session-1", 1, PigType.REGULAR).start(at(1)).complete(1, at(2))
    )
    with pytest.raises(InvalidOperationTransitionError, match="start timestamp"):
        TruckOperation(
            operation_id="operation-1",
            dock_id=DockId.DOCK_1,
            status=TruckOperationStatus.COMPLETED,
            sessions=(completed_session,),
            ended_at=at(3),
        )


def test_operation_activation_sets_timestamp_and_repeated_start_is_rejected() -> None:
    planned = planned_operation()
    active = planned.start(at(0))

    assert planned.status is TruckOperationStatus.PLANNED
    assert active.status is TruckOperationStatus.ACTIVE
    assert active.started_at == at(0)
    with pytest.raises(InvalidOperationTransitionError, match="planned"):
        active.start(at(1))


def test_sessions_cannot_be_added_after_operation_activation() -> None:
    active = planned_operation().start(at(0))
    with pytest.raises(InvalidOperationTransitionError, match="only while"):
        active.add_session(UnloadingSession("session-2", 2, PigType.OPG))
    assert len(active.sessions) == 1


def test_session_order_and_single_active_rule_are_enforced_atomically() -> None:
    active = planned_operation(pig_types=(PigType.OPG, PigType.OPG, PigType.REGULAR)).start(at(0))

    with pytest.raises(InvalidSessionTransitionError, match="Earlier sessions"):
        active.start_session("session-2", at(1))
    assert active.active_session is None

    first_active = active.start_session("session-1", at(1))
    with pytest.raises(InvalidSessionTransitionError, match="already active"):
        first_active.start_session("session-2", at(2))
    assert first_active.session("session-1").status is UnloadingSessionStatus.ACTIVE
    assert first_active.session("session-2").status is UnloadingSessionStatus.PLANNED


def test_active_session_completes_once_and_count_cannot_change() -> None:
    operation = planned_operation().start(at(0)).start_session("session-1", at(1))
    completed_session_operation = operation.complete_session("session-1", 55, at(2))

    assert completed_session_operation.session("session-1").actual_count == 55
    with pytest.raises(InvalidSessionTransitionError, match="active session"):
        completed_session_operation.complete_session("session-1", 56, at(3))
    assert completed_session_operation.session("session-1").actual_count == 55


def test_negative_completion_count_leaves_aggregate_unchanged() -> None:
    operation = planned_operation().start(at(0)).start_session("session-1", at(1))
    with pytest.raises(InvalidCountError, match="Actual count"):
        operation.complete_session("session-1", -1, at(2))
    assert operation.session("session-1").status is UnloadingSessionStatus.ACTIVE
    assert operation.truck_total == 0


def test_operation_completion_requires_no_active_or_planned_sessions() -> None:
    active = planned_operation(pig_types=(PigType.REGULAR, PigType.REGULAR)).start(at(0))
    first_active = active.start_session("session-1", at(1))
    with pytest.raises(InvalidOperationTransitionError, match="active"):
        first_active.complete(at(2))

    first_completed = first_active.complete_session("session-1", 55, at(2))
    with pytest.raises(InvalidOperationTransitionError, match="planned sessions"):
        first_completed.complete(at(3))
    assert first_completed.status is TruckOperationStatus.ACTIVE
    assert first_completed.truck_total == 55


def test_operation_completes_after_all_required_sessions_finish() -> None:
    completed = complete_operation(
        planned_operation(pig_types=(PigType.REGULAR, PigType.REGULAR)),
        (55, 61),
    )

    assert completed.status is TruckOperationStatus.COMPLETED
    assert completed.ended_at == at(5)
    assert completed.truck_total == 116


def test_operation_may_complete_after_remaining_session_is_cancelled() -> None:
    operation = planned_operation(pig_types=(PigType.REGULAR, PigType.OPG)).start(at(0))
    operation = operation.start_session("session-1", at(1))
    operation = operation.complete_session("session-1", 55, at(2))
    operation = operation.cancel_session("session-2", at(3))
    completed = operation.complete(at(4))

    assert completed.status is TruckOperationStatus.COMPLETED
    assert completed.truck_total == 55
    assert completed.session("session-2").status is UnloadingSessionStatus.CANCELLED


def test_planned_operation_cancellation_is_terminal_and_cancels_sessions() -> None:
    planned = planned_operation(pig_types=(PigType.P12, PigType.NAE))
    cancelled = planned.cancel(at(1))

    assert cancelled.status is TruckOperationStatus.CANCELLED
    assert all(session.status is UnloadingSessionStatus.CANCELLED for session in cancelled.sessions)
    assert cancelled.truck_total == 0
    with pytest.raises(InvalidOperationTransitionError, match="terminal"):
        cancelled.add_session(UnloadingSession("session-3", 3, PigType.REGULAR))


def test_active_operation_cancellation_preserves_completed_session_total() -> None:
    operation = planned_operation(pig_types=(PigType.OPG, PigType.REGULAR, PigType.NAE)).start(
        at(0)
    )
    operation = operation.start_session("session-1", at(1))
    operation = operation.complete_session("session-1", 58, at(2))
    operation = operation.start_session("session-2", at(3))

    cancelled = operation.cancel(at(4))

    assert cancelled.status is TruckOperationStatus.CANCELLED
    assert cancelled.session("session-1").status is UnloadingSessionStatus.COMPLETED
    assert cancelled.session("session-1").actual_count == 58
    assert cancelled.session("session-2").status is UnloadingSessionStatus.CANCELLED
    assert cancelled.session("session-3").status is UnloadingSessionStatus.CANCELLED
    assert cancelled.truck_total == 58


def test_cancelled_session_may_be_skipped_because_it_is_terminal() -> None:
    operation = planned_operation(pig_types=(PigType.REGULAR, PigType.OPG)).cancel_session(
        "session-1", at(0)
    )
    operation = operation.start(at(1)).start_session("session-2", at(2))
    assert operation.session("session-2").status is UnloadingSessionStatus.ACTIVE


def test_completed_operation_rejects_every_later_mutation() -> None:
    completed = complete_operation(planned_operation(), (55,))

    mutators = (
        lambda: completed.add_session(UnloadingSession("session-2", 2, PigType.OPG)),
        lambda: completed.start(at(4)),
        lambda: completed.start_session("session-1", at(4)),
        lambda: completed.complete_session("session-1", 56, at(4)),
        lambda: completed.cancel_session("session-1", at(4)),
        lambda: completed.cancel(at(4)),
    )
    for mutate in mutators:
        with pytest.raises(InvalidOperationTransitionError):
            mutate()
    assert completed.truck_total == 55


def test_single_type_regular_truck_totals() -> None:
    operation = complete_operation(
        planned_operation(
            DockId.DOCK_1,
            (PigType.REGULAR, PigType.REGULAR, PigType.REGULAR),
        ),
        (55, 61, 49),
    )

    assert operation.truck_total == 165
    assert operation.total_for(PigType.REGULAR) == 165
    assert operation.total_for(PigType.OPG) == 0
    assert operation.total_for(PigType.P12) == 0
    assert operation.total_for(PigType.NAE) == 0


def test_mixed_opg_and_regular_truck_totals() -> None:
    operation = complete_operation(
        planned_operation(
            DockId.DOCK_2,
            (PigType.OPG, PigType.OPG, PigType.REGULAR),
        ),
        (58, 52, 50),
    )

    assert operation.truck_total == 160
    assert operation.total_for(PigType.OPG) == 110
    assert operation.total_for(PigType.REGULAR) == 50
    assert tuple(total.pig_type for total in operation.totals_by_pig_type) == tuple(PigType)


def test_small_p12_group_uses_exactly_one_session() -> None:
    operation = complete_operation(
        planned_operation(DockId.DOCK_3, (PigType.P12,)),
        (10,),
    )

    assert len(operation.sessions) == 1
    assert operation.truck_total == 10
    assert operation.total_for(PigType.P12) == 10


def test_nae_sessions_are_supported_by_behavior() -> None:
    operation = complete_operation(
        planned_operation(DockId.DOCK_4, (PigType.NAE, PigType.NAE)),
        (12, 8),
    )
    assert operation.total_for(PigType.NAE) == 20


def test_session_summaries_are_immutable_and_ordered() -> None:
    operation = planned_operation(pig_types=(PigType.REGULAR, PigType.OPG))
    summaries = operation.session_summaries
    assert tuple(summary.sequence_number for summary in summaries) == (1, 2)
    with pytest.raises(FrozenInstanceError):
        summaries[0].actual_count = 1  # type: ignore[misc]


def test_truck_operation_is_immutable() -> None:
    operation = planned_operation()
    with pytest.raises(FrozenInstanceError):
        operation.status = TruckOperationStatus.ACTIVE  # type: ignore[misc]
