"""Immutable commands used by the Phase 9.1 operator workflow."""

from __future__ import annotations

from dataclasses import dataclass

from hogflow.application.errors import OperatorInputError
from hogflow.domain import DockId, PigType, TruckOperation, UnloadingSession


@dataclass(frozen=True, slots=True)
class PlannedSession:
    """Operator-entered definition for one planned unloading session."""

    session_id: str
    sequence_number: int
    pig_type: PigType
    expected_count: int | None = None

    def __post_init__(self) -> None:
        self.to_domain()

    def to_domain(self) -> UnloadingSession:
        """Build the validated immutable Phase 8.1 session value."""

        return UnloadingSession(
            session_id=self.session_id,
            sequence_number=self.sequence_number,
            pig_type=self.pig_type,
            expected_count=self.expected_count,
        )


@dataclass(frozen=True, slots=True)
class RegisterTruckCommand:
    """Complete planned truck definition submitted by the operator UI."""

    dock_id: DockId
    operation_id: str
    sessions: tuple[PlannedSession, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.dock_id, DockId):
            DockId.parse(self.dock_id)
        if not isinstance(self.sessions, tuple) or not self.sessions:
            raise OperatorInputError("Operator truck registration requires at least one session.")
        if not all(isinstance(item, PlannedSession) for item in self.sessions):
            raise OperatorInputError(
                "Operator session definitions must be immutable PlannedSession values."
            )
        self.to_operation()

    def to_operation(self) -> TruckOperation:
        """Build one validated Phase 8.1 aggregate without retaining a mutable mirror."""

        operation = TruckOperation(self.operation_id, self.dock_id)
        for session in self.sessions:
            operation = operation.add_session(session.to_domain())
        return operation


__all__ = ["PlannedSession", "RegisterTruckCommand"]
