"""Synchronous application coordination for four isolated unloading docks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from hogflow.counting import LiveCountingResult, LiveCrossingResult, LiveDirectionalCounter
from hogflow.domain import (
    DockId,
    DockOperationRegistry,
    PigType,
    PigTypeTotal,
    TruckOperation,
    TruckOperationStatus,
)
from hogflow.sessions.counting_service import UnloadingSessionCountingService
from hogflow.sessions.errors import SessionCountingIntegrationError
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

CounterFactory = Callable[[DockId, str], LiveDirectionalCounter]
Clock = Callable[[], datetime]


@dataclass(slots=True)
class _DockRuntime:
    """Private resource ownership for one current dock record."""

    source_id: str
    counter: LiveDirectionalCounter
    service: UnloadingSessionCountingService | None = None
    finalized_lifecycles: tuple[FinalizedSessionCountingLifecycle, ...] = ()


class MultiDockRuntimeCoordinator:
    """Route synchronous commands to four isolated dock-scoped runtimes.

    Calls must be serialized by the caller. This class intentionally provides
    no thread-safety, camera acquisition, persistence, scheduling, or UI.
    """

    def __init__(
        self,
        counter_factory: CounterFactory,
        *,
        clock: Clock | None = None,
    ) -> None:
        if not callable(counter_factory):
            raise DockRuntimeConfigurationError("Counter factory must be callable.")
        if clock is not None and not callable(clock):
            raise DockRuntimeConfigurationError("Runtime clock must be callable.")
        self._counter_factory = counter_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._registry = DockOperationRegistry()
        self._runtimes: dict[DockId, _DockRuntime] = {}
        self._closed = False
        self._shutdown_result: MultiDockShutdownResult | None = None

    @property
    def is_closed(self) -> bool:
        """Return whether global shutdown has made commands unavailable."""

        return self._closed

    def register_operation(
        self,
        dock_id: DockId,
        operation: TruckOperation,
        *,
        source_id: str,
    ) -> DockRuntimeSnapshot:
        """Reserve one available dock and construct its isolated counter."""

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
        try:
            validate_session_source_id(source_id)
        except SessionCountingIntegrationError as exc:
            raise DockRuntimeConfigurationError(
                f"{dock.value} source ID must be bounded opaque text."
            ) from exc
        self._validate_source_available(dock, source_id)
        prospective_registry = self._registry.register_operation(operation)

        counter = self._create_counter(dock, source_id)
        self._registry = prospective_registry
        self._runtimes[dock] = _DockRuntime(source_id=source_id, counter=counter)
        return self.runtime_for(dock)

    def start_operation(
        self,
        dock_id: DockId,
        started_at: datetime,
    ) -> DockRuntimeSnapshot:
        """Start only the requested aggregate; no counting lifecycle starts."""

        self._require_open()
        dock, runtime = self._require_runtime(dock_id)
        if runtime.service is not None:
            raise DockRuntimeTransitionError(
                f"{dock.value} already owns an operation counting service."
            )
        prospective_registry = self._registry.start_operation(dock, started_at)
        operation = prospective_registry.operation_for(dock)
        if operation is None:
            raise DockRuntimeTransitionError(
                f"{dock.value} operation startup produced no aggregate."
            )
        service = UnloadingSessionCountingService(
            operation,
            runtime.counter,
            source_id=runtime.source_id,
        )
        self._registry = prospective_registry
        runtime.service = service
        return self.runtime_for(dock)

    def start_session(
        self,
        dock_id: DockId,
        session_id: str,
        crossing_lifecycle_id: str,
        started_at: datetime,
    ) -> SessionCountingLifecycle:
        """Start one fresh session-owned counter lifecycle at one dock."""

        self._require_open()
        dock, runtime, service = self._require_service(dock_id)
        if service.active_lifecycle is not None:
            raise DockRuntimeTransitionError(
                f"{dock.value} already has an active unloading session."
            )
        self._validate_crossing_lifecycle_available(dock, crossing_lifecycle_id)
        prospective_operation = service.operation.start_session(session_id, started_at)
        prospective_registry = self._registry_with_operation(prospective_operation)

        lifecycle = service.start_session(
            session_id,
            crossing_lifecycle_id,
            started_at,
            lifecycle_validator=lambda item: self._validate_started_lifecycle(
                dock,
                runtime,
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
        """Route one explicit crossing result to exactly one dock service."""

        self._require_open()
        dock, _runtime, service = self._require_service(dock_id)
        lifecycle = service.active_lifecycle
        if lifecycle is None:
            raise DockSessionNotActiveError(
                f"{dock.value} has no active unloading session lifecycle."
            )
        if not isinstance(crossing_result, LiveCrossingResult):
            raise DockRuntimeTransitionError(
                f"{dock.value} counting input must be a LiveCrossingResult."
            )
        if crossing_result.source_id != lifecycle.source_id:
            raise DockSourceConflictError(
                f"{dock.value} rejected a crossing result owned by another source."
            )
        if crossing_result.tracker_lifecycle_id != lifecycle.crossing_lifecycle_id:
            raise DockLifecycleConflictError(
                f"{dock.value} rejected a crossing result from another lifecycle."
            )
        last_frame = service.last_processed_frame
        if last_frame is not None and crossing_result.frame_sequence <= last_frame:
            raise DockLifecycleConflictError(f"{dock.value} rejected a stale crossing result.")
        return service.update_counting(crossing_result)

    def complete_session(
        self,
        dock_id: DockId,
        completed_at: datetime,
    ) -> FinalizedSessionCountingLifecycle:
        """Close, transfer, and commit one dock's final session count once."""

        self._require_open()
        dock, _runtime, service = self._require_service(dock_id)
        lifecycle = self._require_active_session(dock, service)
        prospective_operation = service.operation.complete_session(
            lifecycle.session_id,
            service.current_lifecycle_count,
            completed_at,
        )
        prospective_registry = self._registry_with_operation(prospective_operation)
        finalization = service.complete_session(completed_at)
        self._registry = prospective_registry
        return finalization

    def cancel_session(
        self,
        dock_id: DockId,
        cancelled_at: datetime,
    ) -> FinalizedSessionCountingLifecycle:
        """Close and discard one dock's unfinished active-session count."""

        self._require_open()
        dock, _runtime, service = self._require_service(dock_id)
        lifecycle = self._require_active_session(dock, service)
        prospective_operation = service.operation.cancel_session(
            lifecycle.session_id,
            cancelled_at,
        )
        prospective_registry = self._registry_with_operation(prospective_operation)
        finalization = service.cancel_session(cancelled_at)
        self._registry = prospective_registry
        return finalization

    def complete_operation(
        self,
        dock_id: DockId,
        completed_at: datetime,
    ) -> DockRuntimeSnapshot:
        """Complete one truck, release its dock, and retain its terminal view."""

        self._require_open()
        dock, runtime = self._require_runtime(dock_id)
        if runtime.service is not None and runtime.service.active_lifecycle is not None:
            raise DockRuntimeTransitionError(
                f"{dock.value} operation cannot complete with an active session."
            )
        prospective_registry = self._registry.complete_operation(dock, completed_at)
        self._close_counter_for_terminal_operation(dock, runtime)
        self._registry = prospective_registry
        self._release_terminal_service(runtime)
        return self.runtime_for(dock)

    def cancel_operation(
        self,
        dock_id: DockId,
        cancelled_at: datetime,
    ) -> DockRuntimeSnapshot:
        """Cancel one truck; an active session is closed and discarded first."""

        self._require_open()
        dock, runtime = self._require_runtime(dock_id)
        service = runtime.service
        if service is not None and service.active_lifecycle is not None:
            lifecycle = service.active_lifecycle
            prospective_session_operation = service.operation.cancel_session(
                lifecycle.session_id,
                cancelled_at,
            )
            prospective_operation = prospective_session_operation.cancel(cancelled_at)
            prospective_registry = self._registry_with_operation(prospective_operation)
            service.cancel_session(cancelled_at)
        else:
            prospective_registry = self._registry.cancel_operation(dock, cancelled_at)
            self._close_counter_for_terminal_operation(dock, runtime)
        self._registry = prospective_registry
        self._release_terminal_service(runtime)
        return self.runtime_for(dock)

    def runtime_for(self, dock_id: DockId) -> DockRuntimeSnapshot:
        """Return one immutable dock read model, including an available dock."""

        dock = self._require_dock(dock_id)
        return self._snapshot_for(dock)

    def snapshot(self) -> MultiDockRuntimeSnapshot:
        """Return deterministic aggregate state without exposing owned resources."""

        generated_at = self._clock()
        dock_snapshots = tuple(self._snapshot_for(dock) for dock in DockId)
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
        """Close every current counter without fabricating business transitions.

        Active domain sessions are cancelled through Phase 8.2, so unfinished
        totals are discarded without completing their truck operations. Every
        dock is attempted even if another close fails. Recovery after shutdown
        requires a new coordinator.
        """

        if self._shutdown_result is not None:
            self._raise_shutdown_failure(self._shutdown_result)
            return self._shutdown_result

        closed: list[DockId] = []
        failed: list[DockId] = []
        active: list[DockId] = []
        shutdown_at = self._clock()
        for dock in DockId:
            runtime = self._runtimes.get(dock)
            if runtime is None:
                continue
            service = runtime.service
            lifecycle = service.active_lifecycle if service is not None else None
            if lifecycle is not None:
                active.append(dock)
            try:
                if service is not None and lifecycle is not None:
                    prospective_operation = service.operation.cancel_session(
                        lifecycle.session_id,
                        shutdown_at,
                    )
                    prospective_registry = self._registry_with_operation(prospective_operation)
                    service.cancel_session(shutdown_at)
                    self._registry = prospective_registry
                else:
                    runtime.counter.close()
                if runtime.counter.is_started:
                    raise RuntimeError("counter remained active")
            except Exception:
                failed.append(dock)
            else:
                closed.append(dock)

        result = MultiDockShutdownResult(
            closed_docks=tuple(closed),
            failed_docks=tuple(failed),
            active_session_docks=tuple(active),
        )
        self._closed = True
        self._shutdown_result = result
        self._raise_shutdown_failure(result)
        return result

    def _snapshot_for(self, dock: DockId) -> DockRuntimeSnapshot:
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
                f"{dock.value} operation is missing its owned runtime."
            )
        service = runtime.service
        lifecycle = service.active_lifecycle if service is not None else None
        active_session = operation.active_session
        if operation.status.is_terminal:
            status = DockRuntimeStatus.TERMINAL
        elif lifecycle is not None:
            status = DockRuntimeStatus.SESSION_ACTIVE
        elif operation.status is TruckOperationStatus.ACTIVE:
            status = DockRuntimeStatus.OPERATION_ACTIVE
        else:
            status = DockRuntimeStatus.PLANNED
        last_frame = (
            service.last_processed_frame if service is not None and lifecycle is not None else None
        )
        return DockRuntimeSnapshot(
            dock_id=dock,
            available=self._registry.is_available(dock),
            runtime_status=status,
            operation_id=operation.operation_id,
            operation_status=operation.status,
            active_session_id=active_session.session_id if active_session is not None else None,
            active_pig_type=active_session.pig_type if active_session is not None else None,
            current_session_count=(service.current_lifecycle_count if lifecycle is not None else 0),
            truck_total=operation.truck_total,
            totals_by_pig_type=operation.totals_by_pig_type,
            source_id=runtime.source_id,
            crossing_lifecycle_id=(
                lifecycle.crossing_lifecycle_id if lifecycle is not None else None
            ),
            counting_lifecycle_id=(
                lifecycle.counting_lifecycle_id if lifecycle is not None else None
            ),
            last_processed_frame=last_frame,
            finalized_lifecycle_count=len(self._finalized_lifecycles(runtime)),
        )

    def _create_counter(self, dock: DockId, source_id: str) -> LiveDirectionalCounter:
        try:
            counter = self._counter_factory(dock, source_id)
            configuration = counter.configuration
            enabled = configuration.enabled
            is_started = counter.is_started
            required_methods = (
                counter.start,
                counter.update,
                counter.reset,
                counter.close,
                counter.statistics,
                counter.record_preview_failure,
            )
        except Exception as exc:
            raise DockRuntimeConfigurationError(f"{dock.value} counter factory failed.") from exc
        if not enabled or is_started or not all(callable(method) for method in required_methods):
            try:
                counter.close()
            except Exception as exc:
                raise DockRuntimeConfigurationError(
                    f"{dock.value} invalid counter could not be cleaned up."
                ) from exc
            raise DockRuntimeConfigurationError(
                f"{dock.value} requires one enabled, inactive directional counter."
            )
        return counter

    def _validate_source_available(self, dock: DockId, source_id: str) -> None:
        for other_dock, runtime in self._runtimes.items():
            operation = self._registry.operation_for(other_dock)
            if (
                other_dock is not dock
                and operation is not None
                and not operation.is_terminal
                and runtime.source_id == source_id
            ):
                raise DockSourceConflictError(
                    "Source ID already belongs to another active dock runtime."
                )

    def _validate_crossing_lifecycle_available(
        self,
        dock: DockId,
        crossing_lifecycle_id: str,
    ) -> None:
        for other_dock, runtime in self._runtimes.items():
            service = runtime.service
            active = service.active_lifecycle if service is not None else None
            if (
                active is not None
                and active.crossing_lifecycle_id == crossing_lifecycle_id
                and other_dock is not dock
            ):
                raise DockLifecycleConflictError(
                    "Crossing lifecycle already belongs to another active dock."
                )
            if any(
                item.lifecycle.crossing_lifecycle_id == crossing_lifecycle_id
                for item in self._finalized_lifecycles(runtime)
            ):
                raise DockLifecycleConflictError(
                    "A finalized crossing lifecycle cannot be reused by a dock runtime."
                )

    def _validate_started_lifecycle(
        self,
        dock: DockId,
        runtime: _DockRuntime,
        lifecycle: SessionCountingLifecycle,
    ) -> None:
        operation = self._registry.operation_for(dock)
        if (
            operation is None
            or lifecycle.dock_id is not dock
            or lifecycle.operation_id != operation.operation_id
            or lifecycle.source_id != runtime.source_id
        ):
            raise DockLifecycleConflictError(
                f"{dock.value} counter returned mismatched lifecycle provenance."
            )
        for other_dock, other_runtime in self._runtimes.items():
            service = other_runtime.service
            active = service.active_lifecycle if service is not None else None
            if (
                active is not None
                and active.counting_lifecycle_id == lifecycle.counting_lifecycle_id
                and other_dock is not dock
            ):
                raise DockLifecycleConflictError(
                    "Counting lifecycle already belongs to another active dock."
                )
            if any(
                item.lifecycle.counting_lifecycle_id == lifecycle.counting_lifecycle_id
                for item in self._finalized_lifecycles(other_runtime)
            ):
                raise DockLifecycleConflictError(
                    "A finalized counting lifecycle cannot be reused by a dock runtime."
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

    def _close_counter_for_terminal_operation(
        self,
        dock: DockId,
        runtime: _DockRuntime,
    ) -> None:
        try:
            runtime.counter.close()
        except Exception as exc:
            raise DockRuntimeTransitionError(
                f"{dock.value} counter could not close for the terminal operation."
            ) from exc
        if runtime.counter.is_started:
            raise DockRuntimeTransitionError(
                f"{dock.value} counter remained active during the terminal transition."
            )

    @staticmethod
    def _finalized_lifecycles(
        runtime: _DockRuntime,
    ) -> tuple[FinalizedSessionCountingLifecycle, ...]:
        if runtime.service is not None:
            return runtime.service.finalized_lifecycles
        return runtime.finalized_lifecycles

    @staticmethod
    def _release_terminal_service(runtime: _DockRuntime) -> None:
        if runtime.service is None:
            return
        runtime.finalized_lifecycles = runtime.service.finalized_lifecycles
        runtime.service = None

    def _require_runtime(self, dock_id: DockId) -> tuple[DockId, _DockRuntime]:
        dock = self._require_dock(dock_id)
        runtime = self._runtimes.get(dock)
        if runtime is None:
            raise DockRuntimeNotFoundError(f"{dock.value} has no registered runtime.")
        return dock, runtime

    def _require_service(
        self,
        dock_id: DockId,
    ) -> tuple[DockId, _DockRuntime, UnloadingSessionCountingService]:
        dock, runtime = self._require_runtime(dock_id)
        if runtime.service is None:
            raise DockRuntimeTransitionError(f"{dock.value} operation has not started.")
        return dock, runtime, runtime.service

    @staticmethod
    def _require_active_session(
        dock: DockId,
        service: UnloadingSessionCountingService,
    ) -> SessionCountingLifecycle:
        lifecycle = service.active_lifecycle
        if lifecycle is None:
            raise DockSessionNotActiveError(
                f"{dock.value} has no active unloading session lifecycle."
            )
        return lifecycle

    @staticmethod
    def _require_dock(dock_id: DockId) -> DockId:
        if not isinstance(dock_id, DockId):
            raise DockRuntimeNotFoundError("Runtime command requires a supported dock.")
        return dock_id

    def _require_open(self) -> None:
        if self._closed:
            raise DockRuntimeClosedError("Multi-dock runtime is closed.")

    @staticmethod
    def _raise_shutdown_failure(result: MultiDockShutdownResult) -> None:
        if result.failed_docks:
            raise MultiDockShutdownError(
                closed_dock_values=tuple(item.value for item in result.closed_docks),
                failed_dock_values=tuple(item.value for item in result.failed_docks),
            )


__all__ = ["CounterFactory", "MultiDockRuntimeCoordinator"]
