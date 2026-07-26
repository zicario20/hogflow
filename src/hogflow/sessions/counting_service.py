"""Pure application coordination between Phase 8.1 sessions and Phase 7."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from hogflow.core import InputDataError
from hogflow.counting import (
    LiveCountingResult,
    LiveCrossingResult,
    LiveDirectionalCounter,
)
from hogflow.domain import (
    SessionNotFoundError,
    TruckOperation,
    TruckOperationStatus,
    UnloadingSessionStatus,
)
from hogflow.sessions.errors import (
    SessionCountingConfigurationError,
    SessionCountingLifecycleError,
    SessionCountingLifecycleReuseError,
    SessionCountingTransferError,
)
from hogflow.sessions.models import (
    FinalizedSessionCountingLifecycle,
    SessionCountingLifecycle,
    SessionCountingOutcome,
    validate_session_counting_id,
    validate_session_source_id,
)


class UnloadingSessionCountingService:
    """Coordinate one truck operation with one session-owned counter lifecycle.

    The service is deliberately mutable application state around two existing
    boundaries: an immutable ``TruckOperation`` and one Phase 7
    ``LiveDirectionalCounter``. It coordinates only sequential sessions for
    one operation; multi-dock orchestration is outside Phase 8.2.
    """

    def __init__(
        self,
        operation: TruckOperation,
        counter: LiveDirectionalCounter,
        *,
        source_id: str,
        finalized_lifecycles: tuple[FinalizedSessionCountingLifecycle, ...] = (),
    ) -> None:
        if not isinstance(operation, TruckOperation):
            raise SessionCountingConfigurationError(
                "Session counting requires one truck operation."
            )
        if operation.status is not TruckOperationStatus.ACTIVE:
            raise SessionCountingConfigurationError(
                "Session counting requires an active truck operation."
            )
        if operation.active_session is not None:
            raise SessionCountingConfigurationError(
                "An existing active session cannot be adopted without lifecycle provenance."
            )
        validate_session_source_id(source_id)
        if not counter.configuration.enabled:
            raise SessionCountingConfigurationError(
                "Session counting requires an enabled Phase 7 counter."
            )
        if counter.is_started:
            raise SessionCountingConfigurationError(
                "Session counting cannot adopt an already-started counter."
            )
        adopted_finalizations = self._validate_adopted_finalizations(
            operation,
            counter,
            source_id,
            finalized_lifecycles,
        )
        self._operation = operation
        self._counter = counter
        self._source_id = source_id
        self._active_lifecycle: SessionCountingLifecycle | None = None
        self._finalized_lifecycles = adopted_finalizations
        self._current_count = 0
        self._latest_counted_at: datetime | None = None

    @property
    def operation(self) -> TruckOperation:
        """Return the current immutable aggregate value."""

        return self._operation

    @property
    def active_lifecycle(self) -> SessionCountingLifecycle | None:
        """Return the active one-to-one lifecycle binding, when present."""

        return self._active_lifecycle

    @property
    def finalized_lifecycles(self) -> tuple[FinalizedSessionCountingLifecycle, ...]:
        """Return bounded terminal provenance in session completion order."""

        return self._finalized_lifecycles

    @property
    def current_lifecycle_count(self) -> int:
        """Return the last validated Phase 7 total for the active session."""

        return self._current_count

    @property
    def last_processed_frame(self) -> int | None:
        """Return the latest active-lifecycle frame without exposing the counter."""

        if self._active_lifecycle is None:
            return None
        return self._counter.statistics().last_frame_sequence

    def start_session(
        self,
        session_id: str,
        crossing_lifecycle_id: str,
        started_at: datetime,
        *,
        lifecycle_validator: Callable[[SessionCountingLifecycle], None] | None = None,
    ) -> SessionCountingLifecycle:
        """Start one domain session and one fresh Phase 7 lifecycle atomically."""

        if lifecycle_validator is not None and not callable(lifecycle_validator):
            raise SessionCountingConfigurationError("Session lifecycle validator must be callable.")
        if self._active_lifecycle is not None or self._counter.is_started:
            raise SessionCountingLifecycleError(
                "Exactly one counting lifecycle may exist for the active session."
            )
        validate_session_counting_id(crossing_lifecycle_id, "Crossing lifecycle ID")
        if any(
            item.lifecycle.crossing_lifecycle_id == crossing_lifecycle_id
            for item in self._finalized_lifecycles
        ):
            raise SessionCountingLifecycleReuseError(
                "A finalized crossing lifecycle cannot be assigned to another session."
            )

        prospective_operation = self._operation.start_session(session_id, started_at)
        prospective_session = prospective_operation.session(session_id)
        lifecycle_started_at = prospective_session.started_at
        if lifecycle_started_at is None:
            raise SessionCountingLifecycleError(
                "The unloading session did not preserve its lifecycle start."
            )
        try:
            self._counter.start(self._source_id, crossing_lifecycle_id)
            counting_lifecycle_id = self._counter.counting_lifecycle_id
            if any(
                item.lifecycle.counting_lifecycle_id == counting_lifecycle_id
                for item in self._finalized_lifecycles
            ):
                raise SessionCountingLifecycleReuseError(
                    "The counter reused a finalized counting lifecycle identity."
                )
            if (
                self._counter.source_id != self._source_id
                or self._counter.crossing_lifecycle_id != crossing_lifecycle_id
            ):
                raise SessionCountingLifecycleError(
                    "The counter did not preserve the requested lifecycle binding."
                )
            lifecycle = SessionCountingLifecycle(
                operation_id=self._operation.operation_id,
                dock_id=self._operation.dock_id,
                session_id=session_id,
                source_id=self._source_id,
                crossing_lifecycle_id=crossing_lifecycle_id,
                counting_lifecycle_id=counting_lifecycle_id,
                counting_configuration_fingerprint=self._counter.configuration.fingerprint,
                started_at=lifecycle_started_at,
            )
            if lifecycle_validator is not None:
                lifecycle_validator(lifecycle)
        except Exception:
            self._close_after_failed_start()
            raise

        self._operation = prospective_operation
        self._active_lifecycle = lifecycle
        self._current_count = 0
        self._latest_counted_at = None
        return lifecycle

    def update_counting(self, crossing: LiveCrossingResult) -> LiveCountingResult:
        """Apply one validated Phase 7 update to the active session lifecycle."""

        lifecycle = self._require_active_lifecycle()
        if not isinstance(crossing, LiveCrossingResult):
            raise InputDataError("Session counting input must be a LiveCrossingResult.")
        if (
            crossing.source_id != lifecycle.source_id
            or crossing.crossing_lifecycle_id != lifecycle.crossing_lifecycle_id
        ):
            raise SessionCountingLifecycleError(
                "Crossing result does not belong to the active session lifecycle."
            )
        if crossing.captured_at < lifecycle.started_at:
            raise SessionCountingLifecycleError(
                "Crossing result cannot precede the active unloading session."
            )

        result = self._counter.update(crossing)
        if not isinstance(result, LiveCountingResult):
            raise SessionCountingTransferError("Phase 7 returned an unsupported counting result.")
        if (
            result.source_id != lifecycle.source_id
            or result.crossing_lifecycle_id != lifecycle.crossing_lifecycle_id
            or result.counting_lifecycle_id != lifecycle.counting_lifecycle_id
            or result.frame_sequence != crossing.frame_sequence
            or result.captured_at != crossing.captured_at
        ):
            raise SessionCountingTransferError(
                "Phase 7 result does not preserve the active session lifecycle."
            )
        self._current_count = result.lifecycle_directional_count
        self._latest_counted_at = result.captured_at
        return result

    def complete_session(
        self,
        completed_at: datetime,
    ) -> FinalizedSessionCountingLifecycle:
        """Close Phase 7 and transfer its final positive total exactly once."""

        lifecycle = self._require_active_lifecycle()
        prospective_operation = self._operation.complete_session(
            lifecycle.session_id,
            self._current_count,
            completed_at,
        )
        if self._latest_counted_at is not None and completed_at < self._latest_counted_at:
            raise SessionCountingTransferError(
                "Session completion cannot precede its latest counting result."
            )
        finalization = FinalizedSessionCountingLifecycle(
            lifecycle=lifecycle,
            outcome=SessionCountingOutcome.COMPLETED,
            finalized_count=self._current_count,
            ended_at=completed_at,
        )
        self._close_counter_for_terminal_transition()
        self._commit_terminal_transition(prospective_operation, finalization)
        return finalization

    def cancel_session(
        self,
        cancelled_at: datetime,
    ) -> FinalizedSessionCountingLifecycle:
        """Close Phase 7 and discard the active session's unfinished total."""

        lifecycle = self._require_active_lifecycle()
        prospective_operation = self._operation.cancel_session(
            lifecycle.session_id,
            cancelled_at,
        )
        if self._latest_counted_at is not None and cancelled_at < self._latest_counted_at:
            raise SessionCountingTransferError(
                "Session cancellation cannot precede its latest counting result."
            )
        finalization = FinalizedSessionCountingLifecycle(
            lifecycle=lifecycle,
            outcome=SessionCountingOutcome.CANCELLED,
            finalized_count=None,
            ended_at=cancelled_at,
        )
        self._close_counter_for_terminal_transition()
        self._commit_terminal_transition(prospective_operation, finalization)
        return finalization

    def _require_active_lifecycle(self) -> SessionCountingLifecycle:
        if self._active_lifecycle is None or not self._counter.is_started:
            raise SessionCountingLifecycleError(
                "No unloading session owns an active counting lifecycle."
            )
        return self._active_lifecycle

    @staticmethod
    def _validate_adopted_finalizations(
        operation: TruckOperation,
        counter: LiveDirectionalCounter,
        source_id: str,
        finalized_lifecycles: tuple[FinalizedSessionCountingLifecycle, ...],
    ) -> tuple[FinalizedSessionCountingLifecycle, ...]:
        if not isinstance(finalized_lifecycles, tuple) or not all(
            isinstance(item, FinalizedSessionCountingLifecycle) for item in finalized_lifecycles
        ):
            raise SessionCountingConfigurationError(
                "Adopted session lifecycle provenance must be an immutable tuple."
            )
        if not finalized_lifecycles:
            if any(session.status.is_terminal for session in operation.sessions):
                raise SessionCountingConfigurationError(
                    "Terminal sessions require matching counting lifecycle provenance."
                )
            return ()

        session_ids = tuple(item.lifecycle.session_id for item in finalized_lifecycles)
        crossing_ids = tuple(item.lifecycle.crossing_lifecycle_id for item in finalized_lifecycles)
        counting_ids = tuple(item.lifecycle.counting_lifecycle_id for item in finalized_lifecycles)
        if any(
            len(values) != len(set(values)) for values in (session_ids, crossing_ids, counting_ids)
        ):
            raise SessionCountingConfigurationError(
                "Adopted lifecycle provenance cannot contain reused identities."
            )

        sequence_numbers: list[int] = []
        finalized_by_session: dict[str, FinalizedSessionCountingLifecycle] = {}
        for item in finalized_lifecycles:
            lifecycle = item.lifecycle
            if (
                lifecycle.operation_id != operation.operation_id
                or lifecycle.dock_id is not operation.dock_id
                or lifecycle.source_id != source_id
                or lifecycle.counting_configuration_fingerprint != counter.configuration.fingerprint
            ):
                raise SessionCountingConfigurationError(
                    "Adopted lifecycle provenance does not match the operation or shared source."
                )
            try:
                session = operation.session(lifecycle.session_id)
            except SessionNotFoundError as exc:
                raise SessionCountingConfigurationError(
                    "Adopted lifecycle provenance references an unknown session."
                ) from exc
            if item.outcome is SessionCountingOutcome.COMPLETED:
                if (
                    session.status is not UnloadingSessionStatus.COMPLETED
                    or item.finalized_count != session.actual_count
                ):
                    raise SessionCountingConfigurationError(
                        "Completed lifecycle provenance does not match its finalized session."
                    )
            elif session.status is not UnloadingSessionStatus.CANCELLED:
                raise SessionCountingConfigurationError(
                    "Cancelled lifecycle provenance does not match its terminal session."
                )
            sequence_numbers.append(session.sequence_number)
            finalized_by_session[session.session_id] = item

        if sequence_numbers != sorted(sequence_numbers):
            raise SessionCountingConfigurationError(
                "Adopted lifecycle provenance must follow session sequence order."
            )
        terminal_ids = {
            session.session_id
            for session in operation.sessions
            if session.status
            in (
                UnloadingSessionStatus.COMPLETED,
                UnloadingSessionStatus.CANCELLED,
            )
        }
        if terminal_ids != set(finalized_by_session):
            raise SessionCountingConfigurationError(
                "Every terminal session requires exactly one matching lifecycle finalization."
            )
        return finalized_lifecycles

    def _close_after_failed_start(self) -> None:
        if not self._counter.is_started:
            return
        try:
            self._counter.close()
        except Exception as exc:
            raise SessionCountingLifecycleError(
                "Counter cleanup failed after session lifecycle startup."
            ) from exc

    def _close_counter_for_terminal_transition(self) -> None:
        try:
            self._counter.close()
        except Exception as exc:
            raise SessionCountingTransferError(
                "Counter close failed; the session count was not transferred."
            ) from exc
        if self._counter.is_started:
            raise SessionCountingTransferError(
                "Counter remained active; the session count was not transferred."
            )

    def _commit_terminal_transition(
        self,
        operation: TruckOperation,
        finalization: FinalizedSessionCountingLifecycle,
    ) -> None:
        self._operation = operation
        self._finalized_lifecycles = (*self._finalized_lifecycles, finalization)
        self._active_lifecycle = None
        self._current_count = 0
        self._latest_counted_at = None


__all__ = ["UnloadingSessionCountingService"]
