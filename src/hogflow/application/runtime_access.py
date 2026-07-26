"""Single serialized boundary around Phase 8 runtime mutations and snapshots."""

from __future__ import annotations

from datetime import datetime
from threading import RLock

from hogflow.camera.errors import StaleCameraEvidenceError
from hogflow.camera.models import ActiveCountingBinding
from hogflow.counting import LiveCrossingResult
from hogflow.domain import DockId, TruckOperation
from hogflow.sessions import (
    MultiDockRuntimeCoordinator,
    MultiDockRuntimeSnapshot,
    SessionCountingLifecycle,
)


class SerializedMultiDockRuntimeAccess:
    """Serialize operator and camera calls into the caller-serialized lane.

    Detector, tracker, and crossing work occurs outside this boundary. The
    worker enters the lock only to read lane ownership or route one completed
    immutable crossing result. Presentation and application calls use the same
    lock for all Phase 8 mutations and snapshots.
    """

    def __init__(self, coordinator: MultiDockRuntimeCoordinator) -> None:
        if not isinstance(coordinator, MultiDockRuntimeCoordinator):
            raise TypeError("Serialized runtime access requires the Phase 8 coordinator.")
        self._coordinator = coordinator
        self._lock = RLock()

    @property
    def source_id(self) -> str:
        return self.snapshot().counting_lane.source_id

    def snapshot(self) -> MultiDockRuntimeSnapshot:
        with self._lock:
            return self._coordinator.snapshot()

    def register_operation(self, dock_id: DockId, operation: TruckOperation) -> None:
        with self._lock:
            self._coordinator.register_operation(dock_id, operation)

    def start_operation(self, dock_id: DockId, started_at: datetime) -> None:
        with self._lock:
            self._coordinator.start_operation(dock_id, started_at)

    def start_session(
        self,
        dock_id: DockId,
        session_id: str,
        crossing_lifecycle_id: str,
        started_at: datetime,
    ) -> SessionCountingLifecycle:
        with self._lock:
            return self._coordinator.start_session(
                dock_id,
                session_id,
                crossing_lifecycle_id,
                started_at,
            )

    def complete_session(self, dock_id: DockId, completed_at: datetime) -> None:
        with self._lock:
            self._coordinator.complete_session(dock_id, completed_at)

    def cancel_session(self, dock_id: DockId, cancelled_at: datetime) -> None:
        with self._lock:
            self._coordinator.cancel_session(dock_id, cancelled_at)

    def complete_operation(self, dock_id: DockId, completed_at: datetime) -> None:
        with self._lock:
            self._coordinator.complete_operation(dock_id, completed_at)

    def cancel_operation(self, dock_id: DockId, cancelled_at: datetime) -> None:
        with self._lock:
            self._coordinator.cancel_operation(dock_id, cancelled_at)

    def close(self) -> None:
        with self._lock:
            self._coordinator.close()

    def active_binding(self) -> ActiveCountingBinding | None:
        with self._lock:
            lane = self._coordinator.snapshot().counting_lane
            if not lane.occupied:
                return None
            return ActiveCountingBinding(
                dock_id=lane.active_dock_id,
                source_id=lane.source_id,
                crossing_lifecycle_id=lane.crossing_lifecycle_id,
            )

    def route_crossing(
        self,
        expected_binding: ActiveCountingBinding,
        result: LiveCrossingResult,
    ) -> None:
        with self._lock:
            lane = self._coordinator.snapshot().counting_lane
            if (
                not lane.occupied
                or lane.active_dock_id is not expected_binding.dock_id
                or lane.source_id != expected_binding.source_id
                or lane.crossing_lifecycle_id != expected_binding.crossing_lifecycle_id
                or result.source_id != expected_binding.source_id
                or result.crossing_lifecycle_id != expected_binding.crossing_lifecycle_id
            ):
                raise StaleCameraEvidenceError(
                    "Camera crossing evidence no longer belongs to the active lane lifecycle."
                )
            self._coordinator.process_counting_result(expected_binding.dock_id, result)


__all__ = ["SerializedMultiDockRuntimeAccess"]
