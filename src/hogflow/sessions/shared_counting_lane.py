"""Single shared counting-lane ownership for all unloading docks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from hogflow.counting import LiveCountingResult, LiveCrossingResult, LiveDirectionalCounter
from hogflow.domain import DockId, TruckOperation, TruckOperationStatus
from hogflow.sessions.counting_service import UnloadingSessionCountingService
from hogflow.sessions.errors import SessionCountingIntegrationError
from hogflow.sessions.lane_errors import (
    CountingLaneClosedError,
    CountingLaneConfigurationError,
    CountingLaneNotBoundError,
    CountingLaneOccupiedError,
    CountingLaneOwnershipError,
    CountingLaneShutdownError,
    CountingLaneTransitionError,
)
from hogflow.sessions.lane_models import (
    CountingLaneSessionRelease,
    SharedCountingLaneSnapshot,
)
from hogflow.sessions.models import (
    FinalizedSessionCountingLifecycle,
    SessionCountingLifecycle,
    validate_session_source_id,
)

LifecycleValidator = Callable[[SessionCountingLifecycle], None]


@dataclass(slots=True)
class _ActiveLaneBinding:
    """Private mutable reference to the one service currently using the lane."""

    dock_id: DockId
    service: UnloadingSessionCountingService


class SharedCountingLane:
    """Own one source and one Phase 7 counter for one physical corridor.

    The lane may be bound to exactly one unloading session at a time. Docks
    retain their immutable operational state; the lane alone owns the mutable
    counter resource and lends it to a short-lived Phase 8.2 service while
    bound. Calls must be serialized by the caller.
    """

    def __init__(
        self,
        counter: LiveDirectionalCounter,
        *,
        source_id: str,
    ) -> None:
        try:
            validate_session_source_id(source_id)
        except SessionCountingIntegrationError as exc:
            raise CountingLaneConfigurationError(
                "Shared counting-lane source ID must be bounded opaque text."
            ) from exc
        self._validate_counter(counter)
        self._counter = counter
        self._source_id = source_id
        self._active_binding: _ActiveLaneBinding | None = None
        self._closed = False

    @property
    def source_id(self) -> str:
        """Return the one opaque source identity for the physical lane."""

        return self._source_id

    @property
    def is_bound(self) -> bool:
        """Return whether one unloading session currently owns the lane."""

        return self._active_binding is not None

    @property
    def is_closed(self) -> bool:
        """Return whether the shared counter resource has been shut down."""

        return self._closed

    @property
    def active_dock_id(self) -> DockId | None:
        """Return the dock currently assigned to the lane, when occupied."""

        return None if self._active_binding is None else self._active_binding.dock_id

    @property
    def active_lifecycle(self) -> SessionCountingLifecycle | None:
        """Return immutable active lifecycle provenance without exposing service state."""

        if self._active_binding is None:
            return None
        return self._active_binding.service.active_lifecycle

    def bind(
        self,
        dock_id: DockId,
        operation: TruckOperation,
        finalized_lifecycles: tuple[FinalizedSessionCountingLifecycle, ...],
        session_id: str,
        crossing_lifecycle_id: str,
        started_at: datetime,
        *,
        lifecycle_validator: LifecycleValidator | None = None,
    ) -> SessionCountingLifecycle:
        """Bind the idle lane to one session and start one fresh Phase 7 lifecycle."""

        self._require_open()
        dock = self._require_dock(dock_id)
        if self._active_binding is not None:
            active_dock = self._active_binding.dock_id.value
            raise CountingLaneOccupiedError(
                f"Shared counting lane already belongs to {active_dock}."
            )
        if not isinstance(operation, TruckOperation) or operation.dock_id is not dock:
            raise CountingLaneOwnershipError(
                f"{dock.value} cannot bind an operation assigned to another dock."
            )
        if operation.status is not TruckOperationStatus.ACTIVE:
            raise CountingLaneTransitionError(
                "Shared counting lane requires an active truck operation."
            )

        service = UnloadingSessionCountingService(
            operation,
            self._counter,
            source_id=self._source_id,
            finalized_lifecycles=finalized_lifecycles,
        )
        lifecycle = service.start_session(
            session_id,
            crossing_lifecycle_id,
            started_at,
            lifecycle_validator=lifecycle_validator,
        )
        self._active_binding = _ActiveLaneBinding(dock_id=dock, service=service)
        return lifecycle

    def process(
        self,
        dock_id: DockId,
        crossing_result: LiveCrossingResult,
    ) -> LiveCountingResult:
        """Route one result through the service bound to the requested dock."""

        binding = self._require_binding(dock_id)
        return binding.service.update_counting(crossing_result)

    def complete(
        self,
        dock_id: DockId,
        completed_at: datetime,
    ) -> CountingLaneSessionRelease:
        """Finalize one session exactly once and release the shared lane."""

        binding = self._require_binding(dock_id)
        finalization = binding.service.complete_session(completed_at)
        release = CountingLaneSessionRelease(
            operation=binding.service.operation,
            finalization=finalization,
            finalized_lifecycles=binding.service.finalized_lifecycles,
        )
        self._active_binding = None
        return release

    def cancel(
        self,
        dock_id: DockId,
        cancelled_at: datetime,
    ) -> CountingLaneSessionRelease:
        """Discard one unfinished lifecycle and release the shared lane."""

        binding = self._require_binding(dock_id)
        finalization = binding.service.cancel_session(cancelled_at)
        release = CountingLaneSessionRelease(
            operation=binding.service.operation,
            finalization=finalization,
            finalized_lifecycles=binding.service.finalized_lifecycles,
        )
        self._active_binding = None
        return release

    def snapshot(self) -> SharedCountingLaneSnapshot:
        """Return immutable lane ownership and live-count state."""

        if self._active_binding is None:
            return SharedCountingLaneSnapshot(
                source_id=self._source_id,
                occupied=False,
                active_dock_id=None,
                active_operation_id=None,
                active_session_id=None,
                crossing_lifecycle_id=None,
                counting_lifecycle_id=None,
                current_session_count=0,
                last_processed_frame=None,
                closed=self._closed,
            )
        service = self._active_binding.service
        lifecycle = service.active_lifecycle
        if lifecycle is None:
            raise CountingLaneTransitionError(
                "Shared counting lane lost its active lifecycle provenance."
            )
        return SharedCountingLaneSnapshot(
            source_id=self._source_id,
            occupied=True,
            active_dock_id=self._active_binding.dock_id,
            active_operation_id=lifecycle.operation_id,
            active_session_id=lifecycle.session_id,
            crossing_lifecycle_id=lifecycle.crossing_lifecycle_id,
            counting_lifecycle_id=lifecycle.counting_lifecycle_id,
            current_session_count=service.current_lifecycle_count,
            last_processed_frame=service.last_processed_frame,
            closed=self._closed,
        )

    def close(
        self,
        *,
        cancelled_at: datetime | None = None,
    ) -> CountingLaneSessionRelease | None:
        """Close the sole counter; optionally cancel and release an active binding."""

        if self._closed:
            return None
        release: CountingLaneSessionRelease | None = None
        if self._active_binding is not None:
            if cancelled_at is None:
                raise CountingLaneShutdownError(
                    "Closing an occupied counting lane requires a cancellation timestamp."
                )
            try:
                release = self.cancel(self._active_binding.dock_id, cancelled_at)
            except SessionCountingIntegrationError as exc:
                raise CountingLaneShutdownError(
                    "Shared counting session could not close during lane shutdown."
                ) from exc
        else:
            try:
                self._counter.close()
            except Exception as exc:
                raise CountingLaneShutdownError("Shared counting counter could not close.") from exc
        if self._counter.is_started:
            raise CountingLaneShutdownError("Shared counting counter remained active after close.")
        self._closed = True
        return release

    @staticmethod
    def _validate_counter(counter: LiveDirectionalCounter) -> None:
        try:
            enabled = counter.configuration.enabled
            is_started = counter.is_started
            methods = (
                counter.start,
                counter.update,
                counter.reset,
                counter.close,
                counter.statistics,
                counter.record_preview_failure,
            )
        except Exception as exc:
            raise CountingLaneConfigurationError(
                "Shared counting lane requires a valid directional counter."
            ) from exc
        if not enabled or is_started or not all(callable(method) for method in methods):
            raise CountingLaneConfigurationError(
                "Shared counting lane requires one enabled, inactive directional counter."
            )

    def _require_binding(self, dock_id: DockId) -> _ActiveLaneBinding:
        self._require_open()
        dock = self._require_dock(dock_id)
        if self._active_binding is None:
            raise CountingLaneNotBoundError("Shared counting lane has no active session binding.")
        if self._active_binding.dock_id is not dock:
            raise CountingLaneOwnershipError(
                f"{dock.value} does not own the active shared counting lane."
            )
        return self._active_binding

    @staticmethod
    def _require_dock(dock_id: DockId) -> DockId:
        if not isinstance(dock_id, DockId):
            raise CountingLaneOwnershipError(
                "Shared counting-lane commands require a supported dock."
            )
        return dock_id

    def _require_open(self) -> None:
        if self._closed:
            raise CountingLaneClosedError("Shared counting lane is closed.")


__all__ = ["LifecycleValidator", "SharedCountingLane"]
