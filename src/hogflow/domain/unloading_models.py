"""Immutable value objects and entities for truck unloading operations."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum
from re import fullmatch

from hogflow.domain.unloading_errors import (
    InvalidCountError,
    InvalidDockError,
    InvalidIdentifierError,
    InvalidPigTypeError,
    InvalidSessionTransitionError,
    InvalidTimestampError,
)

_OPAQUE_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"


def validate_opaque_id(value: object, label: str) -> str:
    """Return one bounded, non-sensitive identifier or raise a domain error."""

    if not isinstance(value, str) or fullmatch(_OPAQUE_ID_PATTERN, value) is None:
        raise InvalidIdentifierError(
            f"{label} must be 1-64 letters, digits, dots, underscores, or hyphens."
        )
    return value


def validate_non_negative_count(value: object, label: str) -> int:
    """Return one non-negative integer count, rejecting booleans."""

    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InvalidCountError(f"{label} must be a non-negative integer.")
    return value


def validate_positive_integer(value: object, label: str) -> int:
    """Return one positive integer, rejecting booleans."""

    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InvalidSessionTransitionError(f"{label} must be a positive integer.")
    return value


def validate_aware_datetime(value: object, label: str) -> datetime:
    """Return a timezone-aware timestamp."""

    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InvalidTimestampError(f"{label} must be a timezone-aware datetime.")
    return value


class DockId(Enum):
    """The four physical unloading docks supported by Phase 8.1."""

    DOCK_1 = "dock_1"
    DOCK_2 = "dock_2"
    DOCK_3 = "dock_3"
    DOCK_4 = "dock_4"

    @classmethod
    def parse(cls, value: object) -> DockId:
        """Parse a stable dock value without spreading raw integers."""

        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError:
                pass
        raise InvalidDockError("Dock must be one of dock_1, dock_2, dock_3, or dock_4.")

    @property
    def sequence_number(self) -> int:
        """Return the physical one-based dock number for deterministic ordering."""

        return tuple(DockId).index(self) + 1


class PigType(Enum):
    """Stable internal pig-type identifiers."""

    REGULAR = "regular"
    OPG = "opg"
    P12 = "p12"
    NAE = "nae"

    @classmethod
    def parse(cls, value: object) -> PigType:
        """Parse a supported stable pig-type value."""

        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError:
                pass
        raise InvalidPigTypeError("Pig type must be regular, opg, p12, or nae.")


class TruckOperationStatus(Enum):
    """Lifecycle states for one truck unloading operation."""

    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Return whether no further aggregate mutation is allowed."""

        return self in (TruckOperationStatus.COMPLETED, TruckOperationStatus.CANCELLED)


class UnloadingSessionStatus(Enum):
    """Lifecycle states for one ordered unloading session."""

    PLANNED = "planned"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        """Return whether the session cannot become active again."""

        return self in (UnloadingSessionStatus.COMPLETED, UnloadingSessionStatus.CANCELLED)


@dataclass(frozen=True, slots=True)
class UnloadingSessionSummary:
    """Read-only projection of one unloading session."""

    session_id: str
    sequence_number: int
    pig_type: PigType
    status: UnloadingSessionStatus
    expected_count: int | None
    actual_count: int
    started_at: datetime | None
    ended_at: datetime | None

    def __post_init__(self) -> None:
        UnloadingSession(
            session_id=self.session_id,
            sequence_number=self.sequence_number,
            pig_type=self.pig_type,
            status=self.status,
            expected_count=self.expected_count,
            actual_count=self.actual_count,
            started_at=self.started_at,
            ended_at=self.ended_at,
        )


@dataclass(frozen=True, slots=True)
class PigTypeTotal:
    """One deterministic per-type completed-session total."""

    pig_type: PigType
    actual_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.pig_type, PigType):
            raise InvalidPigTypeError("Pig-type total requires a supported pig type.")
        validate_non_negative_count(self.actual_count, "Pig-type total")


@dataclass(frozen=True, slots=True)
class UnloadingSession:
    """One immutable, single-pig-type unloading group."""

    session_id: str
    sequence_number: int
    pig_type: PigType
    status: UnloadingSessionStatus = UnloadingSessionStatus.PLANNED
    expected_count: int | None = None
    actual_count: int = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None

    def __post_init__(self) -> None:
        validate_opaque_id(self.session_id, "Session ID")
        validate_positive_integer(self.sequence_number, "Session sequence number")
        if not isinstance(self.pig_type, PigType):
            raise InvalidPigTypeError("Session pig type must be explicit.")
        if not isinstance(self.status, UnloadingSessionStatus):
            raise InvalidSessionTransitionError("Session status must be explicit.")
        if self.expected_count is not None:
            validate_non_negative_count(self.expected_count, "Expected count")
        validate_non_negative_count(self.actual_count, "Actual count")
        self._validate_lifecycle_fields()

    def _validate_lifecycle_fields(self) -> None:
        if self.started_at is not None:
            validate_aware_datetime(self.started_at, "Session start")
        if self.ended_at is not None:
            validate_aware_datetime(self.ended_at, "Session end")
        if (
            self.started_at is not None
            and self.ended_at is not None
            and self.ended_at < self.started_at
        ):
            raise InvalidTimestampError("Session end cannot precede its start.")

        if self.status is UnloadingSessionStatus.PLANNED:
            if self.started_at is not None or self.ended_at is not None:
                raise InvalidSessionTransitionError(
                    "A planned session cannot have lifecycle timestamps."
                )
        elif self.status is UnloadingSessionStatus.ACTIVE:
            if self.started_at is None or self.ended_at is not None:
                raise InvalidSessionTransitionError(
                    "An active session requires a start and no end."
                )
        elif self.status is UnloadingSessionStatus.COMPLETED:
            if self.started_at is None or self.ended_at is None:
                raise InvalidSessionTransitionError(
                    "A completed session requires start and end timestamps."
                )
        elif self.ended_at is None:
            raise InvalidSessionTransitionError("A cancelled session requires an end timestamp.")

        if self.status is not UnloadingSessionStatus.COMPLETED and self.actual_count != 0:
            raise InvalidCountError("Actual count may be finalized only when a session completes.")

    def start(self, started_at: datetime) -> UnloadingSession:
        """Return the session transitioned from planned to active."""

        if self.status is not UnloadingSessionStatus.PLANNED:
            raise InvalidSessionTransitionError("Only a planned session may be started.")
        timestamp = validate_aware_datetime(started_at, "Session start")
        return replace(
            self,
            status=UnloadingSessionStatus.ACTIVE,
            started_at=timestamp,
        )

    def complete(self, actual_count: int, completed_at: datetime) -> UnloadingSession:
        """Return the active session completed with one finalized count."""

        if self.status is not UnloadingSessionStatus.ACTIVE:
            raise InvalidSessionTransitionError("Only an active session may be completed.")
        count = validate_non_negative_count(actual_count, "Actual count")
        timestamp = validate_aware_datetime(completed_at, "Session completion")
        if self.started_at is not None and timestamp < self.started_at:
            raise InvalidTimestampError("Session completion cannot precede its start.")
        return replace(
            self,
            status=UnloadingSessionStatus.COMPLETED,
            actual_count=count,
            ended_at=timestamp,
        )

    def cancel(self, cancelled_at: datetime) -> UnloadingSession:
        """Return an unfinished session in its terminal cancelled state."""

        if self.status.is_terminal:
            raise InvalidSessionTransitionError("A terminal session cannot be cancelled.")
        timestamp = validate_aware_datetime(cancelled_at, "Session cancellation")
        if self.started_at is not None and timestamp < self.started_at:
            raise InvalidTimestampError("Session cancellation cannot precede its start.")
        return replace(
            self,
            status=UnloadingSessionStatus.CANCELLED,
            ended_at=timestamp,
        )

    def summary(self) -> UnloadingSessionSummary:
        """Return an immutable read model."""

        return UnloadingSessionSummary(
            session_id=self.session_id,
            sequence_number=self.sequence_number,
            pig_type=self.pig_type,
            status=self.status,
            expected_count=self.expected_count,
            actual_count=self.actual_count,
            started_at=self.started_at,
            ended_at=self.ended_at,
        )


__all__ = [
    "DockId",
    "PigType",
    "PigTypeTotal",
    "TruckOperationStatus",
    "UnloadingSession",
    "UnloadingSessionStatus",
    "UnloadingSessionSummary",
]
