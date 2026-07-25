"""Immutable truck-unloading aggregate for Phase 8.1."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from hogflow.domain.unloading_errors import (
    DomainInvariantError,
    DuplicateSessionIdError,
    DuplicateSessionSequenceError,
    InvalidDockError,
    InvalidOperationTransitionError,
    InvalidPigTypeError,
    InvalidSessionTransitionError,
    InvalidTimestampError,
    SessionNotFoundError,
)
from hogflow.domain.unloading_models import (
    DockId,
    PigType,
    PigTypeTotal,
    TruckOperationStatus,
    UnloadingSession,
    UnloadingSessionStatus,
    UnloadingSessionSummary,
    validate_aware_datetime,
    validate_opaque_id,
)


@dataclass(frozen=True, slots=True)
class TruckOperation:
    """Aggregate root for one truck assigned to one physical dock.

    Methods use copy-on-write transitions. The original aggregate is never
    partially mutated when validation fails.
    """

    operation_id: str
    dock_id: DockId
    status: TruckOperationStatus = TruckOperationStatus.PLANNED
    sessions: tuple[UnloadingSession, ...] = ()
    started_at: datetime | None = None
    ended_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_opaque_id(self.operation_id, "Operation ID")
        if not isinstance(self.dock_id, DockId):
            raise InvalidDockError("Truck operation requires a supported dock.")
        if not isinstance(self.status, TruckOperationStatus):
            raise InvalidOperationTransitionError("Operation status must be explicit.")
        if not isinstance(self.sessions, tuple) or not all(
            isinstance(session, UnloadingSession) for session in self.sessions
        ):
            raise DomainInvariantError("Operation sessions must be an immutable tuple.")

        ordered_sessions = tuple(sorted(self.sessions, key=lambda session: session.sequence_number))
        session_ids = tuple(session.session_id for session in ordered_sessions)
        sequences = tuple(session.sequence_number for session in ordered_sessions)
        if len(session_ids) != len(set(session_ids)):
            raise DuplicateSessionIdError("Session IDs must be unique within one truck operation.")
        if len(sequences) != len(set(sequences)):
            raise DuplicateSessionSequenceError(
                "Session sequence numbers must be unique within one truck operation."
            )
        object.__setattr__(self, "sessions", ordered_sessions)
        self._validate_lifecycle()

    def _validate_lifecycle(self) -> None:
        if self.started_at is not None:
            validate_aware_datetime(self.started_at, "Operation start")
        if self.ended_at is not None:
            validate_aware_datetime(self.ended_at, "Operation end")
        if (
            self.started_at is not None
            and self.ended_at is not None
            and self.ended_at < self.started_at
        ):
            raise InvalidTimestampError("Operation end cannot precede its start.")

        active_sessions = tuple(
            session for session in self.sessions if session.status is UnloadingSessionStatus.ACTIVE
        )
        if len(active_sessions) > 1:
            raise DomainInvariantError(
                "A truck operation may have at most one active unloading session."
            )

        if self.status is TruckOperationStatus.PLANNED:
            if self.started_at is not None or self.ended_at is not None:
                raise InvalidOperationTransitionError(
                    "A planned operation cannot have lifecycle timestamps."
                )
            if any(
                session.status in (UnloadingSessionStatus.ACTIVE, UnloadingSessionStatus.COMPLETED)
                for session in self.sessions
            ):
                raise DomainInvariantError(
                    "A planned operation cannot contain active or completed sessions."
                )
        elif self.status is TruckOperationStatus.ACTIVE:
            if self.started_at is None or self.ended_at is not None:
                raise InvalidOperationTransitionError(
                    "An active operation requires a start and no end."
                )
            if not self.sessions:
                raise DomainInvariantError("An active operation requires at least one session.")
        else:
            if self.ended_at is None:
                raise InvalidOperationTransitionError(
                    "A terminal operation requires an end timestamp."
                )
            if self.status is TruckOperationStatus.COMPLETED and self.started_at is None:
                raise InvalidOperationTransitionError(
                    "A completed operation requires a start timestamp."
                )
            if any(not session.status.is_terminal for session in self.sessions):
                raise DomainInvariantError(
                    "A terminal operation cannot contain unfinished sessions."
                )
            if self.status is TruckOperationStatus.COMPLETED and not any(
                session.status is UnloadingSessionStatus.COMPLETED for session in self.sessions
            ):
                raise DomainInvariantError(
                    "A completed operation requires at least one completed session."
                )

        if self.started_at is not None and any(
            session.started_at is not None and session.started_at < self.started_at
            for session in self.sessions
        ):
            raise InvalidTimestampError("A session start cannot precede its operation start.")

        if self.ended_at is not None:
            latest_session_end = max(
                (session.ended_at for session in self.sessions if session.ended_at is not None),
                default=None,
            )
            if latest_session_end is not None and self.ended_at < latest_session_end:
                raise InvalidTimestampError("Operation end cannot precede a session end.")

    @property
    def is_terminal(self) -> bool:
        """Return whether the aggregate rejects every further mutation."""

        return self.status.is_terminal

    @property
    def active_session(self) -> UnloadingSession | None:
        """Return the one active session, when present."""

        return next(
            (
                session
                for session in self.sessions
                if session.status is UnloadingSessionStatus.ACTIVE
            ),
            None,
        )

    @property
    def truck_total(self) -> int:
        """Return the sum of finalized counts from completed sessions only."""

        return sum(
            session.actual_count
            for session in self.sessions
            if session.status is UnloadingSessionStatus.COMPLETED
        )

    @property
    def totals_by_pig_type(self) -> tuple[PigTypeTotal, ...]:
        """Return all supported pig types in stable enum order, including zeroes."""

        return tuple(
            PigTypeTotal(
                pig_type=pig_type,
                actual_count=sum(
                    session.actual_count
                    for session in self.sessions
                    if session.status is UnloadingSessionStatus.COMPLETED
                    and session.pig_type is pig_type
                ),
            )
            for pig_type in PigType
        )

    @property
    def session_summaries(self) -> tuple[UnloadingSessionSummary, ...]:
        """Return deterministic read-only session projections."""

        return tuple(session.summary() for session in self.sessions)

    def total_for(self, pig_type: PigType) -> int:
        """Return the completed-session total for one explicit pig type."""

        if not isinstance(pig_type, PigType):
            raise InvalidPigTypeError("Total lookup requires a supported pig type.")
        return next(
            total.actual_count for total in self.totals_by_pig_type if total.pig_type is pig_type
        )

    def session(self, session_id: str) -> UnloadingSession:
        """Return one session or raise an explicit domain error."""

        validate_opaque_id(session_id, "Session ID")
        for session in self.sessions:
            if session.session_id == session_id:
                return session
        raise SessionNotFoundError("The requested session is not part of this operation.")

    def add_session(self, session: UnloadingSession) -> TruckOperation:
        """Add one planned session while the operation remains planned."""

        self._ensure_not_terminal()
        if self.status is not TruckOperationStatus.PLANNED:
            raise InvalidOperationTransitionError(
                "Sessions may be added only while the operation is planned."
            )
        if not isinstance(session, UnloadingSession):
            raise DomainInvariantError("Only an unloading session may be added.")
        if session.status is not UnloadingSessionStatus.PLANNED:
            raise InvalidSessionTransitionError("A newly added session must be planned.")
        if any(existing.session_id == session.session_id for existing in self.sessions):
            raise DuplicateSessionIdError("Session ID already exists in this truck operation.")
        if any(existing.sequence_number == session.sequence_number for existing in self.sessions):
            raise DuplicateSessionSequenceError(
                "Session sequence number already exists in this truck operation."
            )
        return replace(self, sessions=(*self.sessions, session))

    def start(self, started_at: datetime) -> TruckOperation:
        """Start a planned operation after at least one usable session exists."""

        self._ensure_not_terminal()
        if self.status is not TruckOperationStatus.PLANNED:
            raise InvalidOperationTransitionError("Only a planned operation may be started.")
        if not self.sessions:
            raise InvalidOperationTransitionError(
                "An operation requires at least one session before activation."
            )
        if not any(session.status is UnloadingSessionStatus.PLANNED for session in self.sessions):
            raise InvalidOperationTransitionError(
                "An operation requires at least one planned session before activation."
            )
        timestamp = validate_aware_datetime(started_at, "Operation start")
        self._ensure_not_before_existing_session_end(timestamp)
        return replace(
            self,
            status=TruckOperationStatus.ACTIVE,
            started_at=timestamp,
        )

    def start_session(self, session_id: str, started_at: datetime) -> TruckOperation:
        """Start the next eligible session in deterministic sequence order."""

        self._ensure_active()
        if self.active_session is not None:
            raise InvalidSessionTransitionError("Another unloading session is already active.")
        target = self.session(session_id)
        if target.status is not UnloadingSessionStatus.PLANNED:
            raise InvalidSessionTransitionError("Only a planned session may be started.")
        unfinished_earlier = tuple(
            session
            for session in self.sessions
            if session.sequence_number < target.sequence_number and not session.status.is_terminal
        )
        if unfinished_earlier:
            raise InvalidSessionTransitionError(
                "Earlier sessions must be terminal before this session starts."
            )
        timestamp = validate_aware_datetime(started_at, "Session start")
        if self.started_at is not None and timestamp < self.started_at:
            raise InvalidTimestampError("Session start cannot precede operation start.")
        return self._replace_session(target.start(timestamp))

    def complete_session(
        self,
        session_id: str,
        actual_count: int,
        completed_at: datetime,
    ) -> TruckOperation:
        """Complete the active session with a finalized non-negative count."""

        self._ensure_active()
        target = self.session(session_id)
        completed = target.complete(actual_count, completed_at)
        return self._replace_session(completed)

    def cancel_session(
        self,
        session_id: str,
        cancelled_at: datetime,
    ) -> TruckOperation:
        """Cancel one unfinished session without affecting completed counts."""

        self._ensure_not_terminal()
        target = self.session(session_id)
        timestamp = validate_aware_datetime(cancelled_at, "Session cancellation")
        if self.started_at is not None and timestamp < self.started_at:
            raise InvalidTimestampError("Session cancellation cannot precede operation start.")
        return self._replace_session(target.cancel(timestamp))

    def complete(self, completed_at: datetime) -> TruckOperation:
        """Complete an active operation after all non-cancelled work completed."""

        self._ensure_active()
        if self.active_session is not None:
            raise InvalidOperationTransitionError(
                "An operation cannot complete while a session is active."
            )
        if any(session.status is UnloadingSessionStatus.PLANNED for session in self.sessions):
            raise InvalidOperationTransitionError(
                "An operation cannot complete while planned sessions remain."
            )
        if not any(session.status is UnloadingSessionStatus.COMPLETED for session in self.sessions):
            raise InvalidOperationTransitionError(
                "An operation requires at least one completed session."
            )
        timestamp = validate_aware_datetime(completed_at, "Operation completion")
        self._ensure_end_timestamp(timestamp)
        return replace(
            self,
            status=TruckOperationStatus.COMPLETED,
            ended_at=timestamp,
        )

    def cancel(self, cancelled_at: datetime) -> TruckOperation:
        """Cancel the operation and atomically cancel every unfinished session."""

        self._ensure_not_terminal()
        timestamp = validate_aware_datetime(cancelled_at, "Operation cancellation")
        self._ensure_end_timestamp(timestamp)
        cancelled_sessions = tuple(
            session if session.status.is_terminal else session.cancel(timestamp)
            for session in self.sessions
        )
        return replace(
            self,
            status=TruckOperationStatus.CANCELLED,
            sessions=cancelled_sessions,
            ended_at=timestamp,
        )

    def _replace_session(self, replacement: UnloadingSession) -> TruckOperation:
        return replace(
            self,
            sessions=tuple(
                replacement if session.session_id == replacement.session_id else session
                for session in self.sessions
            ),
        )

    def _ensure_not_terminal(self) -> None:
        if self.is_terminal:
            raise InvalidOperationTransitionError("A terminal truck operation cannot be modified.")

    def _ensure_active(self) -> None:
        if self.status is not TruckOperationStatus.ACTIVE:
            raise InvalidOperationTransitionError(
                "This operation must be active for the requested transition."
            )

    def _ensure_not_before_existing_session_end(self, timestamp: datetime) -> None:
        latest_end = max(
            (session.ended_at for session in self.sessions if session.ended_at is not None),
            default=None,
        )
        if latest_end is not None and timestamp < latest_end:
            raise InvalidTimestampError(
                "Operation timestamp cannot precede an existing session end."
            )

    def _ensure_end_timestamp(self, timestamp: datetime) -> None:
        if self.started_at is not None and timestamp < self.started_at:
            raise InvalidTimestampError("Operation end cannot precede its start.")
        self._ensure_not_before_existing_session_end(timestamp)


__all__ = ["TruckOperation"]
