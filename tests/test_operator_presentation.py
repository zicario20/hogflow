from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass, field

import pytest
from _phase9_helpers import add_positive_count, operator_application, registration

from hogflow.application import (
    DockId,
    OperatorInputError,
    PigType,
    RegisterTruckCommand,
)
from hogflow.domain import InvalidOperationTransitionError
from hogflow.presentation import (
    ConfirmationKind,
    ConfirmationRequest,
    OperatorAction,
    OperatorPresenter,
    OperatorScreen,
    OperatorStatus,
    OperatorView,
    parse_register_truck_form,
    parse_session_plan,
)


@dataclass
class RecordingView:
    screens: list[OperatorScreen] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    confirmations: list[ConfirmationRequest] = field(default_factory=list)
    confirmation_response: bool = True
    close_count: int = 0

    def render(self, screen: OperatorScreen) -> None:
        self.screens.append(screen)

    def show_error(self, message: str) -> None:
        self.errors.append(message)

    def confirm(self, request: ConfirmationRequest) -> bool:
        self.confirmations.append(request)
        return self.confirmation_response

    def close(self) -> None:
        self.close_count += 1


def presenter_fixture():
    application, coordinator = operator_application()
    view = RecordingView()
    presenter = OperatorPresenter(application, view)
    return presenter, application, coordinator, view


def test_recording_view_satisfies_public_view_protocol() -> None:
    assert isinstance(RecordingView(), OperatorView)


def test_empty_snapshot_renders_four_docks_lane_and_zero_totals() -> None:
    presenter, _application, _coordinator, view = presenter_fixture()

    screen = presenter.refresh()

    assert len(screen.docks) == 4
    assert tuple(item.title for item in screen.docks) == (
        "Dock 1",
        "Dock 2",
        "Dock 3",
        "Dock 4",
    )
    assert screen.counting_lane.status == "Idle"
    assert screen.counting_lane.live_count == 0
    assert screen.totals.total_pigs == 0
    assert screen.actions.is_enabled(OperatorAction.REGISTER_TRUCK)
    assert not screen.actions.is_enabled(OperatorAction.START_TRUCK)
    assert not screen.actions.is_enabled(OperatorAction.START_SESSION)
    assert screen.status_message == OperatorStatus.READY.value
    assert view.screens == [screen]


def test_registered_and_active_truck_render_from_fresh_snapshots() -> None:
    presenter, _application, _coordinator, _view = presenter_fixture()
    command = registration(DockId.DOCK_2, (PigType.OPG, PigType.REGULAR))

    planned = presenter.register_truck(command)
    active = presenter.start_truck(DockId.DOCK_2)

    assert planned.docks[1].operation_id == "operator-dock_2"
    assert planned.docks[1].status == "Planned"
    assert planned.docks[1].next_session == "dock_2-session-1"
    assert not planned.actions.register_truck
    assert planned.actions.start_truck
    assert not planned.actions.start_session
    assert planned.actions.cancel_truck
    assert planned.status_message == OperatorStatus.TRUCK_REGISTERED.value
    assert active.docks[1].status == "Operation Active"
    assert not active.actions.start_truck
    assert active.actions.start_session
    assert not active.actions.complete_session
    assert not active.actions.complete_truck
    assert active.status_message == OperatorStatus.TRUCK_STARTED.value
    assert active.counting_lane.status == "Idle"


def test_active_session_renders_lane_owner_pig_type_and_live_count() -> None:
    presenter, _application, coordinator, _view = presenter_fixture()
    presenter.register_truck(registration(DockId.DOCK_3, (PigType.P12,)))
    presenter.start_truck(DockId.DOCK_3)
    presenter.start_session(DockId.DOCK_3, "dock_3-session-1")
    add_positive_count(coordinator, DockId.DOCK_3, (40, 41))

    screen = presenter.refresh(DockId.DOCK_3)

    assert screen.counting_lane.status == "Occupied"
    assert screen.counting_lane.current_dock == "Dock 3"
    assert screen.counting_lane.pig_type == "P-12"
    assert screen.counting_lane.current_session == "dock_3-session-1"
    assert screen.counting_lane.live_count == 2
    assert screen.docks[2].owns_lane
    assert screen.docks[2].is_selected
    assert not screen.actions.register_truck
    assert not screen.actions.start_session
    assert screen.actions.complete_session
    assert screen.actions.cancel_session
    assert not screen.actions.complete_truck
    assert screen.status_message == OperatorStatus.LANE_OCCUPIED.value
    assert screen.docks[2].truck_total == 0


def test_session_release_and_completed_truck_refresh_finalized_totals() -> None:
    presenter, application, coordinator, _view = presenter_fixture()
    presenter.register_truck(registration())
    presenter.start_truck(DockId.DOCK_1)
    presenter.start_session(DockId.DOCK_1, "dock_1-session-1")
    add_positive_count(coordinator, DockId.DOCK_1, (50, 51, 52))

    released = presenter.complete_session(DockId.DOCK_1)
    completed = presenter.complete_truck(DockId.DOCK_1)

    assert released.counting_lane.status == "Idle"
    assert released.totals.total_pigs == 3
    assert released.actions.complete_truck
    assert released.status_message == OperatorStatus.SESSION_COMPLETED.value
    assert application.snapshot().completed_operation_count == 1
    assert completed.totals.completed_trucks == 1
    assert completed.totals.active_trucks == 0
    assert completed.docks[0].status == "Terminal"


def test_cancelled_truck_renders_terminal_without_count() -> None:
    presenter, _application, _coordinator, _view = presenter_fixture()
    presenter.register_truck(registration(DockId.DOCK_4, (PigType.NAE,)))

    screen = presenter.cancel_truck(DockId.DOCK_4)

    assert screen.docks[3].status == "Terminal"
    assert screen.totals.total_pigs == 0
    assert screen.totals.completed_trucks == 0
    assert len(_view.confirmations) == 1
    assert _view.confirmations[0].kind is ConfirmationKind.CANCEL_TRUCK
    assert screen.status_message == OperatorStatus.OPERATION_CANCELLED.value


def test_domain_exception_is_displayed_and_propagated() -> None:
    presenter, _application, _coordinator, view = presenter_fixture()
    presenter.register_truck(registration())

    with pytest.raises(InvalidOperationTransitionError):
        presenter.complete_truck(DockId.DOCK_1)

    assert len(view.errors) == 1
    assert "active" in view.errors[0].lower()


def test_session_plan_parser_supports_mixed_truck_and_optional_expected_count() -> None:
    sessions = parse_session_plan("opg-1,1,opg,60\nregular-2,2,regular\np12-3,3,p12,10")

    command = RegisterTruckCommand(DockId.DOCK_2, "mixed-truck", sessions)
    operation = command.to_operation()

    assert tuple(item.pig_type for item in operation.sessions) == (
        PigType.OPG,
        PigType.REGULAR,
        PigType.P12,
    )
    assert operation.sessions[0].expected_count == 60
    assert operation.sessions[1].expected_count is None


def test_register_form_requires_operation_id_before_application_invocation() -> None:
    with pytest.raises(OperatorInputError, match="operation ID"):
        parse_register_truck_form(DockId.DOCK_1, " ", "session-1,1,regular")


@pytest.mark.parametrize(
    ("value", "message"),
    (
        ("session-1,1,regular\nsession-1,2,opg", "repeats session ID"),
        ("session-1,1,regular\nsession-2,1,opg", "repeats sequence"),
        ("session-1,0,regular", "positive integer"),
        ("session-1,1,invalid", "pig type"),
    ),
)
def test_session_plan_validation_is_specific_and_precedes_application(
    value: str,
    message: str,
) -> None:
    with pytest.raises(OperatorInputError, match=message):
        parse_register_truck_form(DockId.DOCK_1, "truck-1", value)


@pytest.mark.parametrize(
    "value",
    (
        "",
        "missing-fields",
        "session-1,not-an-int,regular",
        "session-1,1,unknown",
    ),
)
def test_session_plan_parser_rejects_invalid_operator_input(value: str) -> None:
    with pytest.raises(OperatorInputError, match="session|Session"):
        parse_session_plan(value)


def test_presentation_import_does_not_eagerly_load_tkinter() -> None:
    sys.modules.pop("tkinter", None)
    module = importlib.reload(importlib.import_module("hogflow.presentation.desktop"))

    assert module is not None
    assert "tkinter" not in sys.modules


def test_cancel_session_decline_preserves_lane_and_count() -> None:
    presenter, application, coordinator, view = presenter_fixture()
    presenter.register_truck(registration())
    presenter.start_truck(DockId.DOCK_1)
    presenter.start_session(DockId.DOCK_1, "dock_1-session-1")
    add_positive_count(coordinator, DockId.DOCK_1, (71, 72))
    view.confirmation_response = False

    screen = presenter.cancel_session(DockId.DOCK_1)

    assert application.snapshot().counting_lane.occupied
    assert application.snapshot().counting_lane.current_session_count == 2
    assert view.confirmations[-1].kind is ConfirmationKind.CANCEL_SESSION
    assert "discarded" in view.confirmations[-1].message
    assert screen.status_message == OperatorStatus.ACTION_NOT_CONFIRMED.value


def test_cancel_session_confirmation_discards_live_count_and_releases_lane() -> None:
    presenter, application, coordinator, view = presenter_fixture()
    presenter.register_truck(registration())
    presenter.start_truck(DockId.DOCK_1)
    presenter.start_session(DockId.DOCK_1, "dock_1-session-1")
    add_positive_count(coordinator, DockId.DOCK_1, (81,))

    screen = presenter.cancel_session(DockId.DOCK_1)

    assert not application.snapshot().counting_lane.occupied
    assert screen.counting_lane.status == "Idle"
    assert screen.status_message == OperatorStatus.SESSION_CANCELLED.value
    assert "unfinished live count (1)" in view.confirmations[-1].message


def test_safe_exit_decline_keeps_active_runtime_open() -> None:
    presenter, application, _coordinator, view = presenter_fixture()
    presenter.register_truck(registration())
    presenter.start_truck(DockId.DOCK_1)
    view.confirmation_response = False

    closed = presenter.request_exit(DockId.DOCK_1)

    assert not closed
    assert not application.snapshot().coordinator_closed
    assert view.close_count == 0
    assert view.confirmations[-1].kind is ConfirmationKind.EXIT_ACTIVE_RUNTIME
    assert "in-memory only" in view.confirmations[-1].message


def test_safe_exit_accepts_lane_discard_and_closes_application() -> None:
    presenter, application, coordinator, view = presenter_fixture()
    presenter.register_truck(registration())
    presenter.start_truck(DockId.DOCK_1)
    presenter.start_session(DockId.DOCK_1, "dock_1-session-1")
    add_positive_count(coordinator, DockId.DOCK_1, (91,))

    closed = presenter.request_exit(DockId.DOCK_1)

    assert closed
    snapshot = application.snapshot()
    assert snapshot.coordinator_closed
    assert not snapshot.counting_lane.occupied
    assert view.close_count == 1
    assert "discarded" in view.confirmations[-1].message
    assert view.screens[-1].status_message == OperatorStatus.APPLICATION_CLOSED.value


def test_presenter_and_view_models_retain_no_runtime_snapshot() -> None:
    presenter, _application, _coordinator, view = presenter_fixture()
    presenter.refresh(DockId.DOCK_2)

    assert "snapshot" not in vars(presenter)
    assert "snapshot" not in vars(view)
