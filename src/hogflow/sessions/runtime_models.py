"""Immutable read models for docks coordinated through one shared lane."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from hogflow.domain import DockId, PigType, PigTypeTotal, TruckOperationStatus
from hogflow.sessions.errors import SessionCountingIntegrationError
from hogflow.sessions.lane_models import SharedCountingLaneSnapshot
from hogflow.sessions.models import (
    validate_session_counting_id,
    validate_session_source_id,
)


class DockRuntimeStatus(str, Enum):
    """Derived operational state of one current dock record."""

    AVAILABLE = "available"
    PLANNED = "planned"
    OPERATION_ACTIVE = "operation_active"
    SESSION_ACTIVE = "session_active"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class DockRuntimeSnapshot:
    """Read-only dock state with optional shared-lane assignment."""

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
        lane_fields = (
            self.source_id,
            self.crossing_lifecycle_id,
            self.counting_lifecycle_id,
        )
        if self.runtime_status is DockRuntimeStatus.SESSION_ACTIVE:
            if self.active_session_id is None or any(value is None for value in lane_fields):
                raise SessionCountingIntegrationError(
                    "An active session requires complete shared-lane provenance."
                )
        elif (
            self.active_session_id is not None
            or self.active_pig_type is not None
            or any(value is not None for value in lane_fields)
            or self.current_session_count != 0
            or self.last_processed_frame is not None
        ):
            raise SessionCountingIntegrationError(
                "A dock without the shared lane cannot expose live session state."
            )
        if self.active_session_id is None and self.active_pig_type is not None:
            raise SessionCountingIntegrationError("Active pig type requires an active session.")
        if self.operation_id is None:
            if (
                self.operation_status is not None
                or self.runtime_status is not DockRuntimeStatus.AVAILABLE
                or not self.available
            ):
                raise SessionCountingIntegrationError(
                    "An empty dock snapshot must be available without operation provenance."
                )
        elif self.operation_status is None:
            raise SessionCountingIntegrationError(
                "A dock operation requires explicit status provenance."
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
            not in (DockRuntimeStatus.OPERATION_ACTIVE, DockRuntimeStatus.SESSION_ACTIVE)
            or self.available
        ):
            raise SessionCountingIntegrationError(
                "An active operation must occupy an active runtime."
            )


@dataclass(frozen=True, slots=True)
class MultiDockRuntimeSnapshot:
    """Deterministic four-dock view plus the single shared counting lane."""

    generated_at: datetime
    dock_snapshots: tuple[DockRuntimeSnapshot, ...]
    counting_lane: SharedCountingLaneSnapshot
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
        if not isinstance(self.counting_lane, SharedCountingLaneSnapshot):
            raise SessionCountingIntegrationError(
                "Runtime snapshot requires one shared counting-lane view."
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
        if self.active_session_count not in (0, 1):
            raise SessionCountingIntegrationError(
                "At most one dock may own the shared counting lane."
            )
        lane_active = 1 if self.counting_lane.occupied else 0
        if self.active_session_count != lane_active:
            raise SessionCountingIntegrationError(
                "Dock session state must match shared counting-lane occupancy."
            )
        if self.counting_lane.occupied:
            dock = self.for_dock(self.counting_lane.active_dock_id)
            if (
                dock.source_id != self.counting_lane.source_id
                or dock.active_session_id != self.counting_lane.active_session_id
                or dock.crossing_lifecycle_id != self.counting_lane.crossing_lifecycle_id
                or dock.counting_lifecycle_id != self.counting_lane.counting_lifecycle_id
                or dock.current_session_count != self.counting_lane.current_session_count
                or dock.last_processed_frame != self.counting_lane.last_processed_frame
            ):
                raise SessionCountingIntegrationError(
                    "Dock session snapshot must mirror shared counting-lane state."
                )
        if self.aggregate_completed_pig_count != sum(
            item.truck_total for item in self.dock_snapshots
        ):
            raise SessionCountingIntegrationError(
                "Aggregate completed count does not match dock snapshots."
            )
        if (
            not isinstance(self.aggregate_totals_by_pig_type, tuple)
            or not all(isinstance(item, PigTypeTotal) for item in self.aggregate_totals_by_pig_type)
            or tuple(item.pig_type for item in self.aggregate_totals_by_pig_type) != tuple(PigType)
        ):
            raise SessionCountingIntegrationError(
                "Aggregate totals must include all supported pig types in stable order."
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
        if self.coordinator_closed != self.counting_lane.closed:
            raise SessionCountingIntegrationError(
                "Coordinator and shared counting lane must close together."
            )

    def for_dock(self, dock_id: DockId | None) -> DockRuntimeSnapshot:
        """Return one dock projection from the immutable full snapshot."""

        if not isinstance(dock_id, DockId):
            raise SessionCountingIntegrationError("Snapshot lookup requires a supported dock.")
        return next(item for item in self.dock_snapshots if item.dock_id is dock_id)


@dataclass(frozen=True, slots=True)
class MultiDockShutdownResult:
    """Bounded shutdown outcome for the one shared counting resource."""

    lane_closed: bool
    cancelled_session_dock: DockId | None

    def __post_init__(self) -> None:
        if not isinstance(self.lane_closed, bool):
            raise SessionCountingIntegrationError("Lane closed state must be boolean.")
        if self.cancelled_session_dock is not None and not isinstance(
            self.cancelled_session_dock,
            DockId,
        ):
            raise SessionCountingIntegrationError(
                "Shutdown cancellation owner must be a supported dock."
            )
        if not self.lane_closed and self.cancelled_session_dock is not None:
            raise SessionCountingIntegrationError(
                "An unclosed lane cannot report a committed session cancellation."
            )

    @property
    def all_closed(self) -> bool:
        """Compatibility alias for successful shared-resource shutdown."""

        return self.lane_closed


__all__ = [
    "DockRuntimeSnapshot",
    "DockRuntimeStatus",
    "MultiDockRuntimeSnapshot",
    "MultiDockShutdownResult",
]
