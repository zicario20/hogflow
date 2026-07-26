from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from _phase9_helpers import LifecycleIdFactory, StepClock

import hogflow.__main__ as operator_main
import hogflow.bootstrap as bootstrap
from hogflow.application import DockId, OperatorApplicationService
from hogflow.presentation import (
    ConfirmationRequest,
    OperatorDesktopView,
    OperatorPresenter,
    OperatorScreen,
)
from hogflow.sessions import MultiDockRuntimeCoordinator, SharedCountingLane


@dataclass
class FakeDesktopView:
    presenter: object | None = None
    screens: list[OperatorScreen] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    confirmations: list[ConfirmationRequest] = field(default_factory=list)
    starts: int = 0
    closes: int = 0

    def bind_presenter(self, presenter: object) -> None:
        self.presenter = presenter

    def start(self) -> None:
        self.starts += 1

    def render(self, screen: OperatorScreen) -> None:
        self.screens.append(screen)

    def show_error(self, message: str) -> None:
        self.errors.append(message)

    def confirm(self, request: ConfirmationRequest) -> bool:
        self.confirmations.append(request)
        return True

    def close(self) -> None:
        self.closes += 1


def test_build_operator_runtime_wires_one_shared_no_camera_lane() -> None:
    runtime = bootstrap.build_operator_runtime(
        clock=StepClock(),
        lifecycle_id_factory=LifecycleIdFactory(),
    )

    assert isinstance(runtime.counting_lane, SharedCountingLane)
    assert isinstance(runtime.coordinator, MultiDockRuntimeCoordinator)
    assert isinstance(runtime.application, OperatorApplicationService)
    assert runtime.counting_lane.source_id == bootstrap.OPERATOR_LANE_SOURCE_ID
    assert (
        runtime.counter.configuration.crossing_configuration_fingerprint
        == bootstrap.NO_CAMERA_CROSSING_CONFIGURATION_FINGERPRINT
    )
    assert not runtime.counter.is_started
    assert not runtime.coordinator.snapshot().counting_lane.occupied


def test_compose_operator_desktop_binds_presenter_and_runs_injected_view() -> None:
    view = FakeDesktopView()

    composition = bootstrap.compose_operator_desktop(
        view_factory=lambda: view,
        clock=StepClock(),
        lifecycle_id_factory=LifecycleIdFactory(),
    )
    composition.run()

    assert isinstance(view, OperatorDesktopView)
    assert isinstance(composition.presenter, OperatorPresenter)
    assert view.presenter is composition.presenter
    assert composition.view is view
    assert view.starts == 1


def test_default_composition_path_uses_local_view_factory(monkeypatch) -> None:
    view = FakeDesktopView()
    monkeypatch.setattr(bootstrap, "create_tk_operator_view", lambda: view)

    composition = bootstrap.compose_operator_desktop(
        clock=StepClock(),
        lifecycle_id_factory=LifecycleIdFactory(),
    )

    assert composition.view is view
    assert view.presenter is composition.presenter


def test_module_entry_point_composes_and_runs_once(monkeypatch) -> None:
    calls: list[str] = []

    class Composition:
        def run(self) -> None:
            calls.append("run")

    monkeypatch.setattr(operator_main, "compose_operator_desktop", Composition)

    assert operator_main.main([]) == 0
    assert calls == ["run"]


def test_module_entry_point_help_does_not_compose_desktop(monkeypatch) -> None:
    monkeypatch.setattr(
        operator_main,
        "compose_operator_desktop",
        lambda: pytest.fail("Help must not create the desktop."),
    )

    with pytest.raises(SystemExit) as error:
        operator_main.main(["--help"])

    assert error.value.code == 0


def test_local_lifecycle_factory_returns_distinct_opaque_ids() -> None:
    factory = bootstrap.LocalCrossingLifecycleIdFactory()

    first = factory(DockId.DOCK_1, "session-1")
    second = factory(DockId.DOCK_1, "session-1")

    assert first.startswith("operator-")
    assert second.startswith("operator-")
    assert first != second
    assert len(first) < 128
