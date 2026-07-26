from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from _phase9_helpers import add_positive_count, operator_application, registration

from hogflow.application import (
    DockId,
    OperatorApplication,
    OperatorInputError,
    PigType,
    PlannedSession,
    RegisterTruckCommand,
)
from hogflow.domain import InvalidCountError, InvalidOperationTransitionError
from hogflow.sessions import DockRuntimeStatus


def test_operator_application_satisfies_public_protocol_and_empty_runtime() -> None:
    application, _coordinator = operator_application()

    assert isinstance(application, OperatorApplication)
    snapshot = application.snapshot()
    assert snapshot.available_dock_count == 4
    assert not snapshot.counting_lane.occupied


def test_registration_command_is_immutable_and_requires_sessions() -> None:
    command = registration()

    with pytest.raises(FrozenInstanceError):
        command.operation_id = "changed"  # type: ignore[misc]
    with pytest.raises(OperatorInputError, match="at least one session"):
        RegisterTruckCommand(DockId.DOCK_1, "truck-empty", ())


def test_planned_session_reuses_phase_8_validation() -> None:
    with pytest.raises(InvalidCountError, match="non-negative integer"):
        PlannedSession("session-1", 1, PigType.P12, expected_count=-1)


def test_register_and_start_truck_return_fresh_coordinator_snapshots() -> None:
    application, _coordinator = operator_application()

    registered = application.register_truck(
        registration(
            DockId.DOCK_2,
            (PigType.OPG, PigType.REGULAR),
        )
    )
    active = application.start_truck(DockId.DOCK_2)

    assert registered.for_dock(DockId.DOCK_2).runtime_status is DockRuntimeStatus.PLANNED
    assert active.for_dock(DockId.DOCK_2).runtime_status is DockRuntimeStatus.OPERATION_ACTIVE
    assert not active.counting_lane.occupied


def test_start_session_binds_lane_and_live_count_refreshes_from_lane_snapshot() -> None:
    application, coordinator = operator_application()
    application.register_truck(registration())
    application.start_truck(DockId.DOCK_1)

    active = application.start_session(DockId.DOCK_1, "dock_1-session-1")
    add_positive_count(coordinator, DockId.DOCK_1, (10, 11))
    refreshed = application.snapshot()

    assert active.counting_lane.occupied
    assert active.counting_lane.active_dock_id is DockId.DOCK_1
    assert refreshed.counting_lane.current_session_count == 2
    assert refreshed.aggregate_completed_pig_count == 0


def test_complete_session_releases_lane_and_transfers_finalized_total() -> None:
    application, coordinator = operator_application()
    application.register_truck(registration())
    application.start_truck(DockId.DOCK_1)
    application.start_session(DockId.DOCK_1, "dock_1-session-1")
    add_positive_count(coordinator, DockId.DOCK_1, (21, 22, 23))

    snapshot = application.complete_session(DockId.DOCK_1)

    assert not snapshot.counting_lane.occupied
    assert snapshot.for_dock(DockId.DOCK_1).truck_total == 3
    assert snapshot.aggregate_completed_pig_count == 3


def test_cancel_session_releases_lane_without_transferring_live_count() -> None:
    application, coordinator = operator_application()
    application.register_truck(registration())
    application.start_truck(DockId.DOCK_1)
    application.start_session(DockId.DOCK_1, "dock_1-session-1")
    add_positive_count(coordinator, DockId.DOCK_1, (31,))

    snapshot = application.cancel_session(DockId.DOCK_1)

    assert not snapshot.counting_lane.occupied
    assert snapshot.for_dock(DockId.DOCK_1).truck_total == 0


def test_complete_and_cancel_truck_use_only_public_runtime_commands() -> None:
    application, _coordinator = operator_application()
    application.register_truck(registration(DockId.DOCK_1))
    application.start_truck(DockId.DOCK_1)
    application.start_session(DockId.DOCK_1, "dock_1-session-1")
    application.complete_session(DockId.DOCK_1)
    completed = application.complete_truck(DockId.DOCK_1)

    application.register_truck(registration(DockId.DOCK_2))
    cancelled = application.cancel_truck(DockId.DOCK_2)

    assert completed.for_dock(DockId.DOCK_1).runtime_status is DockRuntimeStatus.TERMINAL
    assert cancelled.for_dock(DockId.DOCK_2).runtime_status is DockRuntimeStatus.TERMINAL


def test_invalid_operator_transition_propagates_without_fabricating_state() -> None:
    application, _coordinator = operator_application()
    application.register_truck(registration())
    before = application.snapshot()

    with pytest.raises(InvalidOperationTransitionError):
        application.complete_truck(DockId.DOCK_1)

    after = application.snapshot()
    assert after.dock_snapshots == before.dock_snapshots
    assert after.counting_lane == before.counting_lane
