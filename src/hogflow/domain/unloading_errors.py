"""Expected failures for the pure multi-dock unloading domain."""

from hogflow.core import HogFlowError


class UnloadingDomainError(HogFlowError):
    """Base class for expected unloading-domain failures."""


class DomainInvariantError(UnloadingDomainError):
    """Raised when a domain object would violate an aggregate invariant."""


class InvalidIdentifierError(UnloadingDomainError):
    """Raised when an operation or session identifier is invalid."""


class InvalidDockError(UnloadingDomainError):
    """Raised when a dock identifier is unsupported."""


class InvalidPigTypeError(UnloadingDomainError):
    """Raised when a pig type is unsupported."""


class InvalidTimestampError(UnloadingDomainError):
    """Raised when a lifecycle timestamp is invalid."""


class InvalidCountError(UnloadingDomainError):
    """Raised when an expected or actual count is invalid."""


class InvalidOperationTransitionError(UnloadingDomainError):
    """Raised when a truck operation transition is not allowed."""


class InvalidSessionTransitionError(UnloadingDomainError):
    """Raised when an unloading-session transition is not allowed."""


class DuplicateSessionSequenceError(UnloadingDomainError):
    """Raised when two sessions in one operation share a sequence number."""


class DuplicateSessionIdError(UnloadingDomainError):
    """Raised when two sessions in one operation share an identifier."""


class SessionNotFoundError(UnloadingDomainError):
    """Raised when a requested session is absent from an operation."""


class DockOccupiedError(UnloadingDomainError):
    """Raised when a non-terminal operation already occupies a dock."""


class OperationNotFoundError(UnloadingDomainError):
    """Raised when a requested dock has no registered operation."""


class DuplicateOperationIdError(UnloadingDomainError):
    """Raised when current dock records reuse an operation identifier."""


__all__ = [
    "DockOccupiedError",
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
    "SessionNotFoundError",
    "UnloadingDomainError",
]
