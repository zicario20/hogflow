"""Immutable Phase 8.2 lifecycle provenance and finalization records."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from re import fullmatch

from hogflow.domain import DockId
from hogflow.sessions.errors import SessionCountingIntegrationError

_OPAQUE_ID = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
_SOURCE_ID = r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}"
_SHA256 = r"[0-9a-f]{64}"


def validate_session_counting_id(value: object, label: str) -> str:
    """Return bounded opaque text suitable for public lifecycle provenance."""

    if not isinstance(value, str) or fullmatch(_OPAQUE_ID, value) is None:
        raise SessionCountingIntegrationError(f"{label} must be bounded opaque text.")
    return value


def validate_session_source_id(value: object) -> str:
    """Return one source identifier compatible with the Phase 7 contract."""

    if not isinstance(value, str) or fullmatch(_SOURCE_ID, value) is None:
        raise SessionCountingIntegrationError("Session counting source ID must be opaque text.")
    return value


def _aware_datetime(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SessionCountingIntegrationError(f"{label} must be a timezone-aware datetime.")
    return value


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or fullmatch(_SHA256, value) is None:
        raise SessionCountingIntegrationError(f"{label} must be SHA-256 text.")
    return value


class SessionCountingOutcome(str, Enum):
    """Terminal outcome of one session-owned counting lifecycle."""

    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class SessionCountingLifecycle:
    """One active one-to-one binding between a session and Phase 7 lifecycle."""

    operation_id: str
    dock_id: DockId
    session_id: str
    source_id: str
    crossing_lifecycle_id: str
    counting_lifecycle_id: str
    counting_configuration_fingerprint: str
    started_at: datetime

    def __post_init__(self) -> None:
        validate_session_counting_id(self.operation_id, "Operation ID")
        if not isinstance(self.dock_id, DockId):
            raise SessionCountingIntegrationError("Session lifecycle requires a supported dock.")
        validate_session_counting_id(self.session_id, "Session ID")
        validate_session_source_id(self.source_id)
        validate_session_counting_id(
            self.crossing_lifecycle_id,
            "Crossing lifecycle ID",
        )
        validate_session_counting_id(
            self.counting_lifecycle_id,
            "Counting lifecycle ID",
        )
        _sha256(
            self.counting_configuration_fingerprint,
            "Counting configuration fingerprint",
        )
        _aware_datetime(self.started_at, "Session lifecycle start")


@dataclass(frozen=True, slots=True)
class FinalizedSessionCountingLifecycle:
    """Bounded terminal provenance for one completed or cancelled session."""

    lifecycle: SessionCountingLifecycle
    outcome: SessionCountingOutcome
    finalized_count: int | None
    ended_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.lifecycle, SessionCountingLifecycle):
            raise SessionCountingIntegrationError(
                "Finalization requires immutable session lifecycle provenance."
            )
        if not isinstance(self.outcome, SessionCountingOutcome):
            raise SessionCountingIntegrationError("Session counting outcome must be explicit.")
        ended_at = _aware_datetime(self.ended_at, "Session lifecycle end")
        if ended_at < self.lifecycle.started_at:
            raise SessionCountingIntegrationError("Session lifecycle end cannot precede its start.")
        if self.outcome is SessionCountingOutcome.COMPLETED:
            if (
                not isinstance(self.finalized_count, int)
                or isinstance(self.finalized_count, bool)
                or self.finalized_count < 0
            ):
                raise SessionCountingIntegrationError(
                    "Completed session lifecycle requires a non-negative final count."
                )
        elif self.finalized_count is not None:
            raise SessionCountingIntegrationError(
                "Cancelled session lifecycle must discard its unfinished count."
            )


__all__ = [
    "FinalizedSessionCountingLifecycle",
    "SessionCountingLifecycle",
    "SessionCountingOutcome",
]
