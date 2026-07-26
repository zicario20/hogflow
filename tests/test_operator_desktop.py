from __future__ import annotations

from dataclasses import dataclass, field

from _phase9_helpers import operator_application, registration

from hogflow.application import DockId
from hogflow.presentation import (
    ConfirmationRequest,
    OperatorAction,
    OperatorPresenter,
    OperatorScreen,
    TkOperatorView,
)


@dataclass
class FakeVariable:
    value: str = ""

    def set(self, value: str) -> None:
        self.value = value

    def get(self) -> str:
        return self.value


@dataclass
class FakeButton:
    state: str = ""

    def configure(self, *, state: str) -> None:
        self.state = state


@dataclass
class RecordingView:
    screens: list[OperatorScreen] = field(default_factory=list)

    def render(self, screen: OperatorScreen) -> None:
        self.screens.append(screen)

    def show_error(self, _message: str) -> None:
        pass

    def confirm(self, _request: ConfirmationRequest) -> bool:
        return True

    def close(self) -> None:
        pass


def headless_view() -> TkOperatorView:
    view = object.__new__(TkOperatorView)
    view._lane_values = {  # type: ignore[attr-defined]
        key: FakeVariable() for key in ("status", "dock", "truck", "pig_type", "session", "count")
    }
    view._dock_values = {dock: FakeVariable() for dock in DockId}  # type: ignore[attr-defined]
    view._totals_value = FakeVariable()  # type: ignore[attr-defined]
    view._status_value = FakeVariable()  # type: ignore[attr-defined]
    view._session_value = FakeVariable()  # type: ignore[attr-defined]
    view._buttons = {action: FakeButton() for action in OperatorAction}  # type: ignore[attr-defined]
    return view


def test_tk_render_applies_snapshot_button_states_and_lane_indicators() -> None:
    application, _coordinator = operator_application()
    recording = RecordingView()
    presenter = OperatorPresenter(application, recording)
    presenter.register_truck(registration())
    screen = presenter.start_truck(DockId.DOCK_1)
    view = headless_view()

    view.render(screen)

    assert view._buttons[OperatorAction.START_SESSION].state == "normal"  # type: ignore[attr-defined]
    assert view._buttons[OperatorAction.START_TRUCK].state == "disabled"  # type: ignore[attr-defined]
    assert view._buttons[OperatorAction.COMPLETE_SESSION].state == "disabled"  # type: ignore[attr-defined]
    assert view._session_value.get() == "dock_1-session-1"  # type: ignore[attr-defined]
    assert "SELECTED" in view._dock_values[DockId.DOCK_1].get()  # type: ignore[attr-defined]
    assert "Owns Shared Lane: NO" in view._dock_values[DockId.DOCK_1].get()  # type: ignore[attr-defined]
    assert "snapshot" not in vars(view)


def test_tk_render_marks_shared_lane_owner_and_enables_terminal_session_actions() -> None:
    application, _coordinator = operator_application()
    recording = RecordingView()
    presenter = OperatorPresenter(application, recording)
    presenter.register_truck(registration())
    presenter.start_truck(DockId.DOCK_1)
    screen = presenter.start_session(DockId.DOCK_1, "dock_1-session-1")
    view = headless_view()

    view.render(screen)

    dock_text = view._dock_values[DockId.DOCK_1].get()  # type: ignore[attr-defined]
    assert "LANE OWNER" in dock_text
    assert "Owns Shared Lane: YES" in dock_text
    assert view._buttons[OperatorAction.COMPLETE_SESSION].state == "normal"  # type: ignore[attr-defined]
    assert view._buttons[OperatorAction.CANCEL_SESSION].state == "normal"  # type: ignore[attr-defined]
    assert view._buttons[OperatorAction.COMPLETE_TRUCK].state == "disabled"  # type: ignore[attr-defined]
