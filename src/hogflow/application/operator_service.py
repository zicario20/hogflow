"""Stateless operator workflow over the public Phase 8 coordinator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from hogflow.application.models import RegisterTruckCommand
from hogflow.domain import DockId
from hogflow.sessions import MultiDockRuntimeCoordinator, MultiDockRuntimeSnapshot

Clock = Callable[[], datetime]
CrossingLifecycleIdFactory = Callable[[DockId, str], str]


class OperatorApplicationService:
    """Translate operator intent into public coordinator calls.

    The service owns no business state and no snapshot cache. Phase 8 remains
    the only source of truth. A future camera composition root must provide the
    crossing-lifecycle identity factory; Phase 9.1 does not open a camera.
    """

    def __init__(
        self,
        coordinator: MultiDockRuntimeCoordinator,
        *,
        crossing_lifecycle_id_factory: CrossingLifecycleIdFactory,
        clock: Clock | None = None,
    ) -> None:
        if not isinstance(coordinator, MultiDockRuntimeCoordinator):
            raise TypeError("Operator application requires a multi-dock runtime coordinator.")
        if not callable(crossing_lifecycle_id_factory):
            raise TypeError("Crossing lifecycle ID factory must be callable.")
        if clock is not None and not callable(clock):
            raise TypeError("Operator application clock must be callable.")
        self._coordinator = coordinator
        self._crossing_lifecycle_id_factory = crossing_lifecycle_id_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def snapshot(self) -> MultiDockRuntimeSnapshot:
        """Read fresh Phase 8 state without retaining a presentation mirror."""

        return self._coordinator.snapshot()

    def register_truck(self, command: RegisterTruckCommand) -> MultiDockRuntimeSnapshot:
        """Register one complete planned operation through the coordinator."""

        if not isinstance(command, RegisterTruckCommand):
            raise TypeError("Register truck requires an immutable operator command.")
        self._coordinator.register_operation(command.dock_id, command.to_operation())
        return self.snapshot()

    def start_truck(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Start one planned truck using the application clock."""

        self._coordinator.start_operation(dock_id, self._clock())
        return self.snapshot()

    def start_session(self, dock_id: DockId, session_id: str) -> MultiDockRuntimeSnapshot:
        """Bind the shared lane using an externally supplied lifecycle identity."""

        crossing_lifecycle_id = self._crossing_lifecycle_id_factory(dock_id, session_id)
        self._coordinator.start_session(
            dock_id,
            session_id,
            crossing_lifecycle_id,
            self._clock(),
        )
        return self.snapshot()

    def complete_session(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Finalize the active session through Phase 8.2/8.4."""

        self._coordinator.complete_session(dock_id, self._clock())
        return self.snapshot()

    def cancel_session(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Cancel the active session through Phase 8.2/8.4."""

        self._coordinator.cancel_session(dock_id, self._clock())
        return self.snapshot()

    def complete_truck(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Complete one eligible operation through Phase 8.1."""

        self._coordinator.complete_operation(dock_id, self._clock())
        return self.snapshot()

    def cancel_truck(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Cancel one operation through Phase 8.1."""

        self._coordinator.cancel_operation(dock_id, self._clock())
        return self.snapshot()


__all__ = [
    "Clock",
    "CrossingLifecycleIdFactory",
    "OperatorApplicationService",
]
