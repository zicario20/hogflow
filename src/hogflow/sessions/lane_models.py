"""Immutable read and transition models for the shared counting lane."""

from __future__ import annotations

from dataclasses import dataclass

from hogflow.domain import DockId, TruckOperation
from hogflow.sessions.errors import SessionCountingIntegrationError
from hogflow.sessions.models import (
    FinalizedSessionCountingLifecycle,
    validate_session_counting_id,
    validate_session_source_id,
)


@dataclass(frozen=True, slots=True)
class SharedCountingLaneSnapshot:
    """Read-only state of the single physical counting-lane resource."""

    source_id: str
    occupied: bool
    active_dock_id: DockId | None
    active_operation_id: str | None
    active_session_id: str | None
    crossing_lifecycle_id: str | None
    counting_lifecycle_id: str | None
    current_session_count: int
    last_processed_frame: int | None
    closed: bool

    def __post_init__(self) -> None:
        validate_session_source_id(self.source_id)
        if not isinstance(self.occupied, bool) or not isinstance(self.closed, bool):
            raise SessionCountingIntegrationError(
                "Counting-lane occupancy and closed state must be boolean."
            )
        if self.active_dock_id is not None and not isinstance(self.active_dock_id, DockId):
            raise SessionCountingIntegrationError(
                "Counting-lane ownership requires a supported dock."
            )
        for value, label in (
            (self.active_operation_id, "Counting-lane operation ID"),
            (self.active_session_id, "Counting-lane session ID"),
            (self.crossing_lifecycle_id, "Crossing lifecycle ID"),
            (self.counting_lifecycle_id, "Counting lifecycle ID"),
        ):
            if value is not None:
                validate_session_counting_id(value, label)
        if (
            not isinstance(self.current_session_count, int)
            or isinstance(self.current_session_count, bool)
            or self.current_session_count < 0
        ):
            raise SessionCountingIntegrationError(
                "Counting-lane current count must be a non-negative integer."
            )
        if self.last_processed_frame is not None and (
            not isinstance(self.last_processed_frame, int)
            or isinstance(self.last_processed_frame, bool)
            or self.last_processed_frame < 0
        ):
            raise SessionCountingIntegrationError(
                "Counting-lane last frame must be a non-negative integer."
            )
        active_values = (
            self.active_dock_id,
            self.active_operation_id,
            self.active_session_id,
            self.crossing_lifecycle_id,
            self.counting_lifecycle_id,
        )
        if self.occupied:
            if any(value is None for value in active_values):
                raise SessionCountingIntegrationError(
                    "An occupied counting lane requires complete binding provenance."
                )
            if self.closed:
                raise SessionCountingIntegrationError(
                    "A closed counting lane cannot remain occupied."
                )
        elif any(value is not None for value in active_values):
            raise SessionCountingIntegrationError(
                "An idle counting lane cannot expose active binding provenance."
            )
        elif self.current_session_count != 0 or self.last_processed_frame is not None:
            raise SessionCountingIntegrationError(
                "An idle counting lane cannot expose live count or frame state."
            )


@dataclass(frozen=True, slots=True)
class CountingLaneSessionRelease:
    """Terminal session state returned when the shared lane is released."""

    operation: TruckOperation
    finalization: FinalizedSessionCountingLifecycle
    finalized_lifecycles: tuple[FinalizedSessionCountingLifecycle, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.operation, TruckOperation):
            raise SessionCountingIntegrationError(
                "Counting-lane release requires an immutable truck operation."
            )
        if not isinstance(self.finalization, FinalizedSessionCountingLifecycle):
            raise SessionCountingIntegrationError(
                "Counting-lane release requires lifecycle finalization provenance."
            )
        if (
            not isinstance(self.finalized_lifecycles, tuple)
            or not self.finalized_lifecycles
            or not all(
                isinstance(item, FinalizedSessionCountingLifecycle)
                for item in self.finalized_lifecycles
            )
            or self.finalized_lifecycles[-1] != self.finalization
        ):
            raise SessionCountingIntegrationError(
                "Counting-lane release must preserve ordered terminal provenance."
            )
        lifecycle = self.finalization.lifecycle
        if (
            lifecycle.operation_id != self.operation.operation_id
            or lifecycle.dock_id is not self.operation.dock_id
        ):
            raise SessionCountingIntegrationError(
                "Counting-lane release provenance does not match its operation."
            )


__all__ = ["CountingLaneSessionRelease", "SharedCountingLaneSnapshot"]
