"""Synchronous coordination of four docks through one shared counting lane."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from hogflow.counting import LiveCountingResult, LiveCrossingResult
from hogflow.domain import (
    DockId,
    DockOperationRegistry,
    PigType,
    PigTypeTotal,
    TruckOperation,
    TruckOperationStatus,
    UnloadingSessionStatus,
)
from hogflow.sessions.errors import SessionCountingIntegrationError
from hogflow.sessions.lane_errors import (
    CountingLaneOwnershipError,
    CountingLaneShutdownError,
)
from hogflow.sessions.lane_models import SharedCountingLaneSnapshot
from hogflow.sessions.models import (
    FinalizedSessionCountingLifecycle,
    SessionCountingLifecycle,
    validate_session_source_id,
)
from hogflow.sessions.runtime_errors import (
    DockLifecycleConflictError,
    DockOperationMismatchError,
    DockRuntimeClosedError,
    DockRuntimeConfigurationError,
    DockRuntimeNotFoundError,
    DockRuntimeOccupiedError,
    DockRuntimeTransitionError,
    DockSessionNotActiveError,
    DockSourceConflictError,
    MultiDockShutdownError,
)
from hogflow.sessions.runtime_models import (
    DockRuntimeSnapshot,
    DockRuntimeStatus,
    MultiDockRuntimeSnapshot,
    MultiDockShutdownResult,
)
from hogflow.sessions.shared_counting_lane import SharedCountingLane

Clock = Callable[[], datetime]


@dataclass(slots=True)
class _DockRuntime:
    """Private dock state that deliberately owns no counter or camera source."""

    finalized_lifecycles: tuple[FinalizedSessionCountingLifecycle, ...] = ()


class MultiDockRuntimeCoordinator:
    """Route four operational docks through one mutually exclusive counting lane.

    Calls must be serialized by the caller. This class intentionally provides
    no thread-safety, camera acquisition, persistence, scheduling, or UI.
    """

    def __init__(
        self,
        counting_lane: SharedCountingLane,
        *,
        clock: Clock | None = None,
    ) -> None:
        if not isinstance(counting_lane, SharedCountingLane):
            raise DockRuntimeConfigurationError(
                "Multi-dock runtime requires one shared counting lane."
            )
        if counting_lane.is_closed or counting_lane.is_bound:
            raise DockRuntimeConfigurationError(
                "Multi-dock runtime requires one open, idle shared counting lane."
            )
        if clock is not None and not callable(clock):
            raise DockRuntimeConfigurationError("Runtime clock must be callable.")
        self._counting_lane = counting_lane
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._registry = DockOperationRegistry()
        self._runtimes: dict[DockId, _DockRuntime] = {}
        self._closed = False
        self._shutdown_result: MultiDockShutdownResult | None = None

    @property
    def is_closed(self) -> bool:
        """Return whether shutdown has made runtime commands unavailable."""

        return self._closed

    def register_operation(
        self,
        dock_id: DockId,
        operation: TruckOperation,
        *,
        source_id: str | None = None,
    ) -> DockRuntimeSnapshot:
        """Register one planned truck without allocating a dock-owned counter.

        ``source_id`` remains as a migration check for Phase 8.3 callers. When
        supplied it must equal the one shared-lane source; it is not stored as
        dock ownership.
        """

        self._require_open()
        dock = self._require_dock(dock_id)
        if not isinstance(operation, TruckOperation):
            raise DockOperationMismatchError("Dock registration requires a truck operation.")
        if operation.dock_id is not dock:
            raise DockOperationMismatchError(
                f"{dock.value} cannot register an operation assigned to another dock."
            )
        if not self._registry.is_available(dock):
            raise DockRuntimeOccupiedError(f"{dock.value} already has a non-terminal runtime.")
        if source_id is not None:
            try:
                validate_session_source_id(source_id)
            except SessionCountingIntegrationError as exc:
                raise DockRuntimeConfigurationError(
                    "Registered source check must be bounded opaque text."
                ) from exc
            if source_id != self._counting_lane.source_id:
                raise DockSourceConflictError(
                    "Dock registration cannot assign a source other than the shared lane."
                )

        prospective_registry = self._registry.register_operation(operation)
        self._registry = prospective_registry
        self._runtimes[dock] = _DockRuntime()
        return self.runtime_for(dock)

    def start_operation(
        self,
        dock_id: DockId,
        started_at: datetime,
    ) -> DockRuntimeSnapshot:
        """Start only the requested aggregate; the shared lane remains idle."""

        self._require_open()
        dock, _runtime = self._require_runtime(dock_id)
        prospective_registry = self._registry.start_operation(dock, started_at)
        self._registry = prospective_registry
        return self.runtime_for(dock)

    def start_session(
        self,
        dock_id: DockId,
        session_id: str,
        crossing_lifecycle_id: str,
        started_at: datetime,
    ) -> SessionCountingLifecycle:
        """Bind the one shared lane to one dock/session lifecycle."""

        self._require_open()
        dock, runtime = self._require_runtime(dock_id)
        operation = self._require_operation(dock)
        self._validate_crossing_lifecycle_available(crossing_lifecycle_id)
        prospective_operation = operation.start_session(session_id, started_at)
        prospective_registry = self._registry_with_operation(prospective_operation)

        lifecycle = self._counting_lane.bind(
            dock,
            operation,
            runtime.finalized_lifecycles,
            session_id,
            crossing_lifecycle_id,
            started_at,
            lifecycle_validator=lambda item: self._validate_started_lifecycle(
                dock,
                operation,
                item,
            ),
        )
        self._registry = prospective_registry
        return lifecycle

    def process_counting_result(
        self,
        dock_id: DockId,
        crossing_result: LiveCrossingResult,
    ) -> LiveCountingResult:
        """Route one result to the dock that explicitly owns the shared lane."""

        self._require_open()
        dock, _runtime = self._require_runtime(dock_id)
        lane = self._require_lane_owner(dock)
        if not isinstance(crossing_result, LiveCrossingResult):
            raise DockRuntimeTransitionError(
                f"{dock.value} counting input must be a LiveCrossingResult."
            )
        if crossing_result.source_id != lane.source_id:
            raise DockSourceConflictError(
                f"{dock.value} rejected a result outside the shared counting source."
            )
        if crossing_result.crossing_lifecycle_id != lane.crossing_lifecycle_id:
            raise DockLifecycleConflictError(
                f"{dock.value} rejected a result from another counting-lane lifecycle."
            )
        if (
            lane.last_processed_frame is not None
            and crossing_result.frame_sequence <= lane.last_processed_frame
        ):
            raise DockLifecycleConflictError(f"{dock.value} rejected a stale crossing result.")
        return self._counting_lane.process(dock, crossing_result)

    def complete_session(
        self,
        dock_id: DockId,
        completed_at: datetime,
    ) -> FinalizedSessionCountingLifecycle:
        """Finalize one session count exactly once and release the shared lane."""

        self._require_open()
        dock, runtime = self._require_runtime(dock_id)
        lane = self._require_lane_owner(dock)
        operation = self._require_operation(dock)
        if lane.active_session_id is None:
            raise DockSessionNotActiveError(f"{dock.value} has no active unloading session.")
        prospective_operation = operation.complete_session(
            lane.active_session_id,
            lane.current_session_count,
            completed_at,
        )
        prospective_registry = self._registry_with_operation(prospective_operation)
        release = self._counting_lane.complete(dock, completed_at)
        self._validate_lane_release(prospective_operation, release.operation)
        self._registry = prospective_registry
        runtime.finalized_lifecycles = release.finalized_lifecycles
        return release.finalization

    def cancel_session(
        self,
        dock_id: DockId,
        cancelled_at: datetime,
    ) -> FinalizedSessionCountingLifecycle:
        """Discard one unfinished lifecycle and release the shared lane."""

        self._require_open()
        dock, runtime = self._require_runtime(dock_id)
        lane = self._require_lane_owner(dock)
        operation = self._require_operation(dock)
        if lane.active_session_id is None:
            raise DockSessionNotActiveError(f"{dock.value} has no active unloading session.")
        prospective_operation = operation.cancel_session(
            lane.active_session_id,
            cancelled_at,
        )
        prospective_registry = self._registry_with_operation(prospective_operation)
        release = self._counting_lane.cancel(dock, cancelled_at)
        self._validate_lane_release(prospective_operation, release.operation)
        self._registry = prospective_registry
        runtime.finalized_lifecycles = release.finalized_lifecycles
        return release.finalization

    def complete_operation(
        self,
        dock_id: DockId,
        completed_at: datetime,
    ) -> DockRuntimeSnapshot:
        """Complete one truck without changing the idle/shared lane resource."""

        self._require_open()
        dock, _runtime = self._require_runtime(dock_id)
        if self._counting_lane.active_dock_id is dock:
            raise DockRuntimeTransitionError(
                f"{dock.value} operation cannot complete while it owns the shared lane."
            )
        self._registry = self._registry.complete_operation(dock, completed_at)
        return self.runtime_for(dock)

    def cancel_operation(
        self,
        dock_id: DockId,
        cancelled_at: datetime,
    ) -> DockRuntimeSnapshot:
        """Cancel one truck, releasing the lane first only when that dock owns it."""

        self._require_open()
        dock, runtime = self._require_runtime(dock_id)
        if self._counting_lane.active_dock_id is dock:
            lane = self._counting_lane.snapshot()
            operation = self._require_operation(dock)
            if lane.active_session_id is None:
                raise DockSessionNotActiveError(f"{dock.value} has no active unloading session.")
            prospective_session_operation = operation.cancel_session(
                lane.active_session_id,
                cancelled_at,
            )
            prospective_operation = prospective_session_operation.cancel(cancelled_at)
            prospective_registry = self._registry_with_operation(prospective_operation)
            release = self._counting_lane.cancel(dock, cancelled_at)
            self._validate_lane_release(prospective_session_operation, release.operation)
            runtime.finalized_lifecycles = release.finalized_lifecycles
            self._registry = prospective_registry
        else:
            self._registry = self._registry.cancel_operation(dock, cancelled_at)
        return self.runtime_for(dock)

    def runtime_for(self, dock_id: DockId) -> DockRuntimeSnapshot:
        """Return one immutable dock view without exposing the shared counter."""

        dock = self._require_dock(dock_id)
        return self._snapshot_for(dock, self._counting_lane.snapshot())

    def snapshot(self) -> MultiDockRuntimeSnapshot:
        """Return deterministic dock totals and one shared counting-lane view."""

        generated_at = self._clock()
        lane = self._counting_lane.snapshot()
        dock_snapshots = tuple(self._snapshot_for(dock, lane) for dock in DockId)
        totals = tuple(
            PigTypeTotal(
                pig_type,
                sum(
                    next(
                        total.actual_count
                        for total in item.totals_by_pig_type
                        if total.pig_type is pig_type
                    )
                    for item in dock_snapshots
                ),
            )
            for pig_type in PigType
        )
        return MultiDockRuntimeSnapshot(
            generated_at=generated_at,
            dock_snapshots=dock_snapshots,
            counting_lane=lane,
            occupied_dock_count=sum(not item.available for item in dock_snapshots),
            available_dock_count=sum(item.available for item in dock_snapshots),
            active_operation_count=sum(
                item.operation_status is TruckOperationStatus.ACTIVE for item in dock_snapshots
            ),
            active_session_count=sum(
                item.runtime_status is DockRuntimeStatus.SESSION_ACTIVE for item in dock_snapshots
            ),
            aggregate_completed_pig_count=sum(item.truck_total for item in dock_snapshots),
            aggregate_totals_by_pig_type=totals,
            coordinator_closed=self._closed,
        )

    def close(self) -> MultiDockShutdownResult:
        """Close the one shared counter without fabricating completed counts."""

        if self._shutdown_result is not None:
            return self._shutdown_result

        shutdown_at = self._clock()
        cancelled_dock = self._counting_lane.active_dock_id
        prospective_registry: DockOperationRegistry | None = None
        prospective_operation: TruckOperation | None = None
        if cancelled_dock is not None:
            lane = self._counting_lane.snapshot()
            if lane.active_session_id is None:
                raise MultiDockShutdownError(bound_dock_value=cancelled_dock.value)
            operation = self._require_operation(cancelled_dock)
            prospective_operation = operation.cancel_session(
                lane.active_session_id,
                shutdown_at,
            )
            prospective_registry = self._registry_with_operation(prospective_operation)
        try:
            release = self._counting_lane.close(
                cancelled_at=shutdown_at if cancelled_dock is not None else None
            )
        except CountingLaneShutdownError as exc:
            raise MultiDockShutdownError(
                bound_dock_value=(None if cancelled_dock is None else cancelled_dock.value)
            ) from exc

        if cancelled_dock is not None:
            if release is None or prospective_operation is None or prospective_registry is None:
                raise MultiDockShutdownError(bound_dock_value=cancelled_dock.value)
            self._validate_lane_release(prospective_operation, release.operation)
            self._runtimes[cancelled_dock].finalized_lifecycles = release.finalized_lifecycles
            self._registry = prospective_registry
        result = MultiDockShutdownResult(
            lane_closed=True,
            cancelled_session_dock=cancelled_dock,
        )
        self._closed = True
        self._shutdown_result = result
        return result

    def _snapshot_for(
        self,
        dock: DockId,
        lane: SharedCountingLaneSnapshot,
    ) -> DockRuntimeSnapshot:
        operation = self._registry.operation_for(dock)
        runtime = self._runtimes.get(dock)
        if operation is None:
            return DockRuntimeSnapshot(
                dock_id=dock,
                available=True,
                runtime_status=DockRuntimeStatus.AVAILABLE,
                operation_id=None,
                operation_status=None,
                active_session_id=None,
                active_pig_type=None,
                next_planned_session_id=None,
                next_planned_pig_type=None,
                operation_can_start_session=False,
                operation_can_complete=False,
                current_session_count=0,
                truck_total=0,
                totals_by_pig_type=tuple(PigTypeTotal(item, 0) for item in PigType),
                source_id=None,
                crossing_lifecycle_id=None,
                counting_lifecycle_id=None,
                last_processed_frame=None,
                finalized_lifecycle_count=0,
            )
        if runtime is None:
            raise DockRuntimeTransitionError(
                f"{dock.value} operation is missing its runtime provenance."
            )

        owns_lane = lane.occupied and lane.active_dock_id is dock
        active_session = operation.active_session if owns_lane else None
        planned_sessions = tuple(
            session
            for session in operation.sessions
            if session.status is UnloadingSessionStatus.PLANNED
        )
        next_planned_session = planned_sessions[0] if planned_sessions else None
        if operation.status.is_terminal:
            status = DockRuntimeStatus.TERMINAL
        elif owns_lane:
            status = DockRuntimeStatus.SESSION_ACTIVE
        elif operation.status is TruckOperationStatus.ACTIVE:
            status = DockRuntimeStatus.OPERATION_ACTIVE
        else:
            status = DockRuntimeStatus.PLANNED
        return DockRuntimeSnapshot(
            dock_id=dock,
            available=self._registry.is_available(dock),
            runtime_status=status,
            operation_id=operation.operation_id,
            operation_status=operation.status,
            active_session_id=(None if active_session is None else active_session.session_id),
            active_pig_type=(None if active_session is None else active_session.pig_type),
            next_planned_session_id=(
                None if next_planned_session is None else next_planned_session.session_id
            ),
            next_planned_pig_type=(
                None if next_planned_session is None else next_planned_session.pig_type
            ),
            operation_can_start_session=(
                operation.status is TruckOperationStatus.ACTIVE
                and not lane.occupied
                and next_planned_session is not None
            ),
            operation_can_complete=(
                operation.status is TruckOperationStatus.ACTIVE
                and not owns_lane
                and not planned_sessions
                and any(
                    session.status is UnloadingSessionStatus.COMPLETED
                    for session in operation.sessions
                )
            ),
            current_session_count=lane.current_session_count if owns_lane else 0,
            truck_total=operation.truck_total,
            totals_by_pig_type=operation.totals_by_pig_type,
            source_id=lane.source_id if owns_lane else None,
            crossing_lifecycle_id=lane.crossing_lifecycle_id if owns_lane else None,
            counting_lifecycle_id=lane.counting_lifecycle_id if owns_lane else None,
            last_processed_frame=lane.last_processed_frame if owns_lane else None,
            finalized_lifecycle_count=len(runtime.finalized_lifecycles),
        )

    def _validate_crossing_lifecycle_available(
        self,
        crossing_lifecycle_id: str,
    ) -> None:
        for runtime in self._runtimes.values():
            if any(
                item.lifecycle.crossing_lifecycle_id == crossing_lifecycle_id
                for item in runtime.finalized_lifecycles
            ):
                raise DockLifecycleConflictError(
                    "A finalized crossing lifecycle cannot be reused by the shared lane."
                )

    def _validate_started_lifecycle(
        self,
        dock: DockId,
        operation: TruckOperation,
        lifecycle: SessionCountingLifecycle,
    ) -> None:
        if (
            lifecycle.dock_id is not dock
            or lifecycle.operation_id != operation.operation_id
            or lifecycle.source_id != self._counting_lane.source_id
        ):
            raise DockLifecycleConflictError(
                f"{dock.value} shared counter returned mismatched lifecycle provenance."
            )
        for runtime in self._runtimes.values():
            if any(
                item.lifecycle.counting_lifecycle_id == lifecycle.counting_lifecycle_id
                for item in runtime.finalized_lifecycles
            ):
                raise DockLifecycleConflictError(
                    "A finalized counting lifecycle cannot be reused by the shared lane."
                )

    def _registry_with_operation(
        self,
        replacement: TruckOperation,
    ) -> DockOperationRegistry:
        return DockOperationRegistry(
            tuple(
                replacement if current.dock_id is replacement.dock_id else current
                for current in self._registry.operations
            )
        )

    def _require_lane_owner(self, dock: DockId) -> SharedCountingLaneSnapshot:
        lane = self._counting_lane.snapshot()
        if not lane.occupied:
            raise DockSessionNotActiveError(
                f"{dock.value} has no active shared counting-lane lifecycle."
            )
        if lane.active_dock_id is not dock:
            raise CountingLaneOwnershipError(
                f"{dock.value} does not own the active shared counting lane."
            )
        return lane

    def _require_runtime(self, dock_id: DockId) -> tuple[DockId, _DockRuntime]:
        dock = self._require_dock(dock_id)
        runtime = self._runtimes.get(dock)
        if runtime is None:
            raise DockRuntimeNotFoundError(f"{dock.value} has no registered runtime.")
        return dock, runtime

    def _require_operation(self, dock: DockId) -> TruckOperation:
        operation = self._registry.operation_for(dock)
        if operation is None:
            raise DockRuntimeNotFoundError(f"{dock.value} has no registered operation.")
        return operation

    @staticmethod
    def _validate_lane_release(
        expected: TruckOperation,
        actual: TruckOperation,
    ) -> None:
        if actual != expected:
            raise DockRuntimeTransitionError(
                "Shared counting-lane transition did not preserve the prospective operation."
            )

    @staticmethod
    def _require_dock(dock_id: DockId) -> DockId:
        if not isinstance(dock_id, DockId):
            raise DockRuntimeNotFoundError("Runtime command requires a supported dock.")
        return dock_id

    def _require_open(self) -> None:
        if self._closed:
            raise DockRuntimeClosedError("Multi-dock runtime is closed.")


__all__ = ["MultiDockRuntimeCoordinator"]
