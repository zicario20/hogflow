"""Pure operational domain concepts independent from vision and persistence."""

from hogflow.domain.dock_registry import DockOperationRegistry
from hogflow.domain.truck_operation import TruckOperation
from hogflow.domain.unloading_errors import (
    DockOccupiedError,
    DomainInvariantError,
    DuplicateOperationIdError,
    DuplicateSessionIdError,
    DuplicateSessionSequenceError,
    InvalidCountError,
    InvalidDockError,
    InvalidIdentifierError,
    InvalidOperationTransitionError,
    InvalidPigTypeError,
    InvalidSessionTransitionError,
    InvalidTimestampError,
    OperationNotFoundError,
    SessionNotFoundError,
    UnloadingDomainError,
)
from hogflow.domain.unloading_models import (
    DockId,
    PigType,
    PigTypeTotal,
    TruckOperationStatus,
    UnloadingSession,
    UnloadingSessionStatus,
    UnloadingSessionSummary,
)

__all__ = [
    "DockId",
    "DockOccupiedError",
    "DockOperationRegistry",
    "DomainInvariantError",
    "DuplicateOperationIdError",
    "DuplicateSessionIdError",
    "DuplicateSessionSequenceError",
    "InvalidCountError",
    "InvalidDockError",
    "InvalidIdentifierError",
    "InvalidOperationTransitionError",
    "InvalidPigTypeError",
    "InvalidSessionTransitionError",
    "InvalidTimestampError",
    "OperationNotFoundError",
    "PigType",
    "PigTypeTotal",
    "SessionNotFoundError",
    "TruckOperation",
    "TruckOperationStatus",
    "UnloadingDomainError",
    "UnloadingSession",
    "UnloadingSessionStatus",
    "UnloadingSessionSummary",
]
