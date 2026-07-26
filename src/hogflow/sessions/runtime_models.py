"""Immutable read models for the synchronous four-dock runtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from hogflow.domain import DockId, PigType, PigTypeTotal, TruckOperationStatus
from hogflow.sessions.errors import SessionCountingIntegrationError
from hogflow.sessions.models import (
    validate_session_counting_id,
    validate_session_source_id,
)


class DockRuntimeStatus(str, Enum):
    """Derived state of one current dock record."""

    AVAILABLE = "available"
    PLANNED = "planned"
    OPERATION_ACTIVE = "operation_active"
    SESSION_ACTIVE = "session_active"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class DockRuntimeSnapshot:
    """Read-only projection of one dock without mutable service objects."""

    dock_id: DockId
    available: bool
    runtime_status: DockRuntimeStatus
    operation_id: str | None
    operation_status: TruckOperationStatus | None
    active_session_id: str | None
    active_pig_type: PigType | None
    current_session_count: int
    truck_total: int
    totals_by_pig_type: tuple[PigTypeTotal, ...]
    source_id: str | None
    crossing_lifecycle_id: str | None
    counting_lifecycle_id: str | None
    last_processed_frame: int | None
    finalized_lifecycle_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.dock_id, DockId):
            raise SessionCountingIntegrationError("Runtime snapshot requires a supported dock.")
        if not isinstance(self.available, bool):
            raise SessionCountingIntegrationError("Dock availability must be boolean.")
        if not isinstance(self.runtime_status, DockRuntimeStatus):
            raise SessionCountingIntegrationError("Dock runtime status must be explicit.")
        if self.operation_id is not None:
            validate_session_counting_id(self.operation_id, "Runtime operation ID")
        if self.operation_status is not None and not isinstance(
            self.operation_status,
            TruckOperationStatus,
        ):
            raise SessionCountingIntegrationError("Operation status must be explicit.")
        if self.active_session_id is not None:
            validate_session_counting_id(self.active_session_id, "Active session ID")
        if self.active_pig_type is not None and not isinstance(
            self.active_pig_type,
            PigType,
        ):
            raise SessionCountingIntegrationError("Active pig type must be explicit.")
        if self.source_id is not None:
            validate_session_source_id(self.source_id)
        for lifecycle_id, label in (
            (self.crossing_lifecycle_id, "Crossing lifecycle ID"),
            (self.counting_lifecycle_id, "Counting lifecycle ID"),
        ):
            if lifecycle_id is not None:
                validate_session_counting_id(lifecycle_id, label)
        for value, label in (
            (self.current_session_count, "Current session count"),
            (self.truck_total, "Truck total"),
            (self.finalized_lifecycle_count, "Finalized lifecycle count"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise SessionCountingIntegrationError(f"{label} must be a non-negative integer.")
        if self.last_processed_frame is not None and (
            not isinstance(self.last_processed_frame, int)
            or isinstance(self.last_processed_frame, bool)
            or self.last_processed_frame < 0
        ):
            raise SessionCountingIntegrationError(
                "Last processed frame must be a non-negative integer."
            )
        if (
            not isinstance(self.totals_by_pig_type, tuple)
            or not all(isinstance(item, PigTypeTotal) for item in self.totals_by_pig_type)
            or tuple(item.pig_type for item in self.totals_by_pig_type) != tuple(PigType)
        ):
            raise SessionCountingIntegrationError(
                "Runtime pig-type totals must include all supported types in stable order."
            )
        if sum(item.actual_count for item in self.totals_by_pig_type) != self.truck_total:
            raise SessionCountingIntegrationError(
                "Runtime pig-type totals must equal the completed truck total."
            )
        if (self.crossing_lifecycle_id is None) != (self.counting_lifecycle_id is None):
            raise SessionCountingIntegrationError(
                "Crossing and counting lifecycle IDs must appear together."
            )
        if self.crossing_lifecycle_id is None and (
            self.current_session_count != 0 or self.last_processed_frame is not None
        ):
            raise SessionCountingIntegrationError(
                "Inactive sessions cannot expose live count or frame state."
            )
        if self.active_session_id is None and self.active_pig_type is not None:
            raise SessionCountingIntegrationError("Active pig type requires an active session.")
        if (self.active_session_id is None) != (
            self.runtime_status is not DockRuntimeStatus.SESSION_ACTIVE
        ):
            raise SessionCountingIntegrationError(
                "Active session identity must match the derived runtime status."
            )
        if self.runtime_status is DockRuntimeStatus.SESSION_ACTIVE and (
            self.crossing_lifecycle_id is None
        ):
            raise SessionCountingIntegrationError(
                "An active session requires lifecycle provenance."
            )
        if self.operation_id is None:
            if (
                self.operation_status is not None
                or self.source_id is not None
                or self.runtime_status is not DockRuntimeStatus.AVAILABLE
                or not self.available
            ):
                raise SessionCountingIntegrationError(
                    "An empty dock snapshot must be available without runtime provenance."
                )
        elif self.operation_status is None or self.source_id is None:
            raise SessionCountingIntegrationError(
                "A dock operation requires status and source provenance."
            )
        elif self.operation_status.is_terminal:
            if self.runtime_status is not DockRuntimeStatus.TERMINAL or not self.available:
                raise SessionCountingIntegrationError(
                    "A terminal operation must expose an available terminal runtime."
                )
        elif self.operation_status is TruckOperationStatus.PLANNED:
            if self.runtime_status is not DockRuntimeStatus.PLANNED or self.available:
                raise SessionCountingIntegrationError(
                    "A planned operation must occupy a planned runtime."
                )
        elif (
            self.runtime_status
            not in (
                DockRuntimeStatus.OPERATION_ACTIVE,
                DockRuntimeStatus.SESSION_ACTIVE,
            )
            or self.available
        ):
            raise SessionCountingIntegrationError(
                "An active operation must occupy an active runtime."
            )


@dataclass(frozen=True, slots=True)
class MultiDockRuntimeSnapshot:
    """Deterministic aggregate view across the four current dock records."""

    generated_at: datetime
    dock_snapshots: tuple[DockRuntimeSnapshot, ...]
    occupied_dock_count: int
    available_dock_count: int
    active_operation_count: int
    active_session_count: int
    aggregate_completed_pig_count: int
    aggregate_totals_by_pig_type: tuple[PigTypeTotal, ...]
    coordinator_closed: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.generated_at, datetime)
            or self.generated_at.tzinfo is None
            or self.generated_at.utcoffset() is None
        ):
            raise SessionCountingIntegrationError("Runtime snapshot time must be timezone-aware.")
        if tuple(item.dock_id for item in self.dock_snapshots) != tuple(DockId):
            raise SessionCountingIntegrationError(
                "Runtime snapshot must contain Dock 1 through Dock 4 in order."
            )
        for value, label in (
            (self.occupied_dock_count, "Occupied dock count"),
            (self.available_dock_count, "Available dock count"),
            (self.active_operation_count, "Active operation count"),
            (self.active_session_count, "Active session count"),
            (self.aggregate_completed_pig_count, "Aggregate completed count"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise SessionCountingIntegrationError(f"{label} must be a non-negative integer.")
        if self.occupied_dock_count + self.available_dock_count != len(DockId):
            raise SessionCountingIntegrationError(
                "Occupied and available dock counts must cover all docks."
            )
        if (
            not isinstance(self.aggregate_totals_by_pig_type, tuple)
            or not all(isinstance(item, PigTypeTotal) for item in self.aggregate_totals_by_pig_type)
            or tuple(item.pig_type for item in self.aggregate_totals_by_pig_type) != tuple(PigType)
        ):
            raise SessionCountingIntegrationError(
                "Aggregate totals must include all supported pig types in stable order."
            )
        if self.occupied_dock_count != sum(not item.available for item in self.dock_snapshots):
            raise SessionCountingIntegrationError(
                "Occupied dock count does not match dock snapshots."
            )
        if self.active_operation_count != sum(
            item.operation_status is TruckOperationStatus.ACTIVE for item in self.dock_snapshots
        ):
            raise SessionCountingIntegrationError(
                "Active operation count does not match dock snapshots."
            )
        if self.active_session_count != sum(
            item.runtime_status is DockRuntimeStatus.SESSION_ACTIVE for item in self.dock_snapshots
        ):
            raise SessionCountingIntegrationError(
                "Active session count does not match dock snapshots."
            )
        if self.aggregate_completed_pig_count != sum(
            item.truck_total for item in self.dock_snapshots
        ):
            raise SessionCountingIntegrationError(
                "Aggregate completed count does not match dock snapshots."
            )
        for total in self.aggregate_totals_by_pig_type:
            expected = sum(
                next(
                    item.actual_count
                    for item in dock.totals_by_pig_type
                    if item.pig_type is total.pig_type
                )
                for dock in self.dock_snapshots
            )
            if total.actual_count != expected:
                raise SessionCountingIntegrationError(
                    "Aggregate pig-type total does not match dock snapshots."
                )
        if not isinstance(self.coordinator_closed, bool):
            raise SessionCountingIntegrationError("Coordinator closed state must be boolean.")

    def for_dock(self, dock_id: DockId) -> DockRuntimeSnapshot:
        """Return one dock projection from the immutable full snapshot."""

        if not isinstance(dock_id, DockId):
            raise SessionCountingIntegrationError("Snapshot lookup requires a supported dock.")
        return next(item for item in self.dock_snapshots if item.dock_id is dock_id)


@dataclass(frozen=True, slots=True)
class MultiDockShutdownResult:
    """Bounded shutdown outcome; active business state is never fabricated."""

    closed_docks: tuple[DockId, ...]
    failed_docks: tuple[DockId, ...]
    active_session_docks: tuple[DockId, ...]

    def __post_init__(self) -> None:
        for values, label in (
            (self.closed_docks, "Closed docks"),
            (self.failed_docks, "Failed docks"),
            (self.active_session_docks, "Active-session docks"),
        ):
            if not isinstance(values, tuple) or not all(
                isinstance(item, DockId) for item in values
            ):
                raise SessionCountingIntegrationError(f"{label} must be immutable dock IDs.")
            if len(values) != len(set(values)):
                raise SessionCountingIntegrationError(f"{label} cannot contain duplicates.")
            if values != tuple(sorted(values, key=lambda item: item.sequence_number)):
                raise SessionCountingIntegrationError(f"{label} must use deterministic order.")
        if set(self.closed_docks) & set(self.failed_docks):
            raise SessionCountingIntegrationError(
                "A dock cannot be both closed and failed during shutdown."
            )

    @property
    def all_closed(self) -> bool:
        """Return whether every current runtime counter closed successfully."""

        return not self.failed_docks


__all__ = [
    "DockRuntimeSnapshot",
    "DockRuntimeStatus",
    "MultiDockRuntimeSnapshot",
    "MultiDockShutdownResult",
]
