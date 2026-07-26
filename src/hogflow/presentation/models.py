"""Immutable display models for the Phase 9.1 operator desktop."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OperatorAction(str, Enum):
    """Explicit desktop actions whose availability comes from one snapshot."""

    REGISTER_TRUCK = "register_truck"
    START_TRUCK = "start_truck"
    START_SESSION = "start_session"
    COMPLETE_SESSION = "complete_session"
    CANCEL_SESSION = "cancel_session"
    COMPLETE_TRUCK = "complete_truck"
    CANCEL_TRUCK = "cancel_truck"
    CONFIGURE_SOURCE = "configure_source"
    START_PIPELINE = "start_pipeline"
    STOP_PIPELINE = "stop_pipeline"
    REFRESH = "refresh"
    EXIT = "exit"


class OperatorStatus(str, Enum):
    """Transient operator feedback; never a second business-state store."""

    READY = "Ready"
    LANE_OCCUPIED = "Lane Occupied"
    TRUCK_REGISTERED = "Truck Registered"
    TRUCK_STARTED = "Truck Started"
    SESSION_STARTED = "Session Started — Lane Occupied"
    SESSION_COMPLETED = "Session Completed — Lane Released"
    SESSION_CANCELLED = "Session Cancelled — Unfinished live count discarded"
    TRUCK_COMPLETED = "Truck Completed"
    OPERATION_CANCELLED = "Operation Cancelled"
    SOURCE_CONFIGURED = "Video Source Configured"
    PIPELINE_STARTED = "Counting Pipeline Started"
    PIPELINE_STOPPED = "Counting Pipeline Stopped"
    ACTION_NOT_CONFIRMED = "Action Not Confirmed"
    APPLICATION_CLOSED = "Application Closed"
    ERROR = "Error"


class ConfirmationKind(str, Enum):
    """Destructive operator actions that require explicit acknowledgement."""

    CANCEL_SESSION = "cancel_session"
    CANCEL_TRUCK = "cancel_truck"
    EXIT_ACTIVE_RUNTIME = "exit_active_runtime"


@dataclass(frozen=True, slots=True)
class ConfirmationRequest:
    """Bounded, presentation-only explanation for one destructive action."""

    kind: ConfirmationKind
    title: str
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ConfirmationKind):
            raise ValueError("Confirmation kind must be explicit.")
        for value, label in ((self.title, "title"), (self.message, "message")):
            if not isinstance(value, str) or not value.strip() or len(value) > 512:
                raise ValueError(f"Confirmation {label} must be bounded text.")


@dataclass(frozen=True, slots=True)
class OperatorActionState:
    """Snapshot-derived availability for every operator control."""

    register_truck: bool
    start_truck: bool
    start_session: bool
    complete_session: bool
    cancel_session: bool
    complete_truck: bool
    cancel_truck: bool
    configure_source: bool
    start_pipeline: bool
    stop_pipeline: bool
    refresh: bool
    exit: bool

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, bool)
            for value in (
                self.register_truck,
                self.start_truck,
                self.start_session,
                self.complete_session,
                self.cancel_session,
                self.complete_truck,
                self.cancel_truck,
                self.configure_source,
                self.start_pipeline,
                self.stop_pipeline,
                self.refresh,
                self.exit,
            )
        ):
            raise ValueError("Operator action availability must be boolean.")

    def is_enabled(self, action: OperatorAction) -> bool:
        """Return one explicit control state without string inference."""

        if not isinstance(action, OperatorAction):
            raise ValueError("Operator action lookup requires an explicit action.")
        return bool(getattr(self, action.value))


@dataclass(frozen=True, slots=True)
class CountingLanePanel:
    """Display-only projection of the shared counting lane."""

    status: str
    current_dock: str
    truck: str
    pig_type: str
    current_session: str
    live_count: int


@dataclass(frozen=True, slots=True)
class DockPanel:
    """Display-only projection for one of the four operational docks."""

    dock_id: str
    title: str
    operation_id: str
    status: str
    pig_type: str
    truck_total: int
    current_session: str
    next_session: str
    next_pig_type: str
    is_selected: bool
    owns_lane: bool


@dataclass(frozen=True, slots=True)
class TotalsPanel:
    """Display-only finalized totals from one Phase 8 snapshot."""

    total_pigs: int
    totals_by_pig_type: tuple[tuple[str, int], ...]
    completed_trucks: int
    active_trucks: int


@dataclass(frozen=True, slots=True)
class CameraPipelinePanel:
    """Display-only camera and one-worker pipeline projection."""

    source: str
    camera_status: str
    pipeline_status: str
    frames_acquired: int
    frames_processed: int
    last_error: str
    active_crossing_lifecycle: str


@dataclass(frozen=True, slots=True)
class OperatorScreen:
    """One complete, immutable rendering input produced by a manual refresh."""

    counting_lane: CountingLanePanel
    docks: tuple[DockPanel, ...]
    totals: TotalsPanel
    camera_pipeline: CameraPipelinePanel
    selected_dock_id: str
    actions: OperatorActionState
    status_message: str
    generated_at: str

    def __post_init__(self) -> None:
        if len(self.docks) != 4:
            raise ValueError("Operator screen requires exactly four dock panels.")
        if sum(item.is_selected for item in self.docks) != 1:
            raise ValueError("Operator screen requires exactly one selected dock.")
        if not isinstance(self.actions, OperatorActionState):
            raise ValueError("Operator screen requires explicit action availability.")
        if not isinstance(self.status_message, str) or not self.status_message.strip():
            raise ValueError("Operator screen requires an operator status message.")


__all__ = [
    "ConfirmationKind",
    "ConfirmationRequest",
    "CameraPipelinePanel",
    "CountingLanePanel",
    "DockPanel",
    "OperatorAction",
    "OperatorActionState",
    "OperatorScreen",
    "OperatorStatus",
    "TotalsPanel",
]
