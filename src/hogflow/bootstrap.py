"""Executable Phase 9 desktop composition without camera or persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Callable
from uuid import uuid4

from hogflow.application import (
    Clock,
    CrossingLifecycleIdFactory,
    DockId,
    OperatorApplicationService,
)
from hogflow.counting import (
    LifecycleDirectionalCounter,
    LiveCountingConfiguration,
    LiveCrossingDirection,
)
from hogflow.presentation import (
    OperatorDesktopView,
    OperatorPresenter,
    create_tk_operator_view,
)
from hogflow.sessions import MultiDockRuntimeCoordinator, SharedCountingLane

OPERATOR_LANE_SOURCE_ID = "shared_operator_lane"
NO_CAMERA_CROSSING_CONFIGURATION_FINGERPRINT = sha256(
    b"hogflow-phase-9.2-no-camera-crossing-configuration"
).hexdigest()

ViewFactory = Callable[[], OperatorDesktopView]


class LocalCrossingLifecycleIdFactory:
    """Create opaque local lifecycle IDs for the no-camera executable."""

    def __call__(self, _dock_id: DockId, _session_id: str) -> str:
        return f"operator-{uuid4().hex}"


@dataclass(frozen=True, slots=True)
class OperatorRuntimeComposition:
    """Application resources created once by the executable composition root."""

    counter: LifecycleDirectionalCounter
    counting_lane: SharedCountingLane
    coordinator: MultiDockRuntimeCoordinator
    application: OperatorApplicationService


@dataclass(frozen=True, slots=True)
class OperatorDesktopComposition:
    """Fully wired one-window Operator MVP composition."""

    runtime: OperatorRuntimeComposition
    presenter: OperatorPresenter
    view: OperatorDesktopView

    def run(self) -> None:
        """Start the manually refreshed local desktop."""

        self.view.start()


def build_operator_runtime(
    *,
    clock: Clock | None = None,
    lifecycle_id_factory: CrossingLifecycleIdFactory | None = None,
) -> OperatorRuntimeComposition:
    """Build the one shared no-camera runtime used by the executable MVP."""

    configuration = LiveCountingConfiguration(
        enabled=True,
        positive_direction=LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
        crossing_configuration_fingerprint=NO_CAMERA_CROSSING_CONFIGURATION_FINGERPRINT,
    )
    counter = LifecycleDirectionalCounter(configuration)
    lane = SharedCountingLane(counter, source_id=OPERATOR_LANE_SOURCE_ID)
    coordinator = MultiDockRuntimeCoordinator(lane, clock=clock)
    application = OperatorApplicationService(
        coordinator,
        crossing_lifecycle_id_factory=(lifecycle_id_factory or LocalCrossingLifecycleIdFactory()),
        clock=clock,
    )
    return OperatorRuntimeComposition(
        counter=counter,
        counting_lane=lane,
        coordinator=coordinator,
        application=application,
    )


def compose_operator_desktop(
    *,
    view_factory: ViewFactory | None = None,
    clock: Callable[[], datetime] | None = None,
    lifecycle_id_factory: CrossingLifecycleIdFactory | None = None,
) -> OperatorDesktopComposition:
    """Create and wire lane → coordinator → application → presenter → view."""

    runtime = build_operator_runtime(
        clock=clock,
        lifecycle_id_factory=lifecycle_id_factory,
    )
    try:
        view = (view_factory or create_tk_operator_view)()
        presenter = OperatorPresenter(runtime.application, view)
        view.bind_presenter(presenter)
    except Exception:
        runtime.application.shutdown()
        raise
    return OperatorDesktopComposition(
        runtime=runtime,
        presenter=presenter,
        view=view,
    )


__all__ = [
    "LocalCrossingLifecycleIdFactory",
    "NO_CAMERA_CROSSING_CONFIGURATION_FINGERPRINT",
    "OPERATOR_LANE_SOURCE_ID",
    "OperatorDesktopComposition",
    "OperatorRuntimeComposition",
    "build_operator_runtime",
    "compose_operator_desktop",
]
