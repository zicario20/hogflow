"""Snapshot-driven presenter for the Phase 9 operator workflow."""

from __future__ import annotations

from collections.abc import Callable

from hogflow.application import (
    DockId,
    DockRuntimeStatus,
    ExpectedOperatorError,
    MultiDockRuntimeSnapshot,
    OperatorApplication,
    PigType,
    RegisterTruckCommand,
    TruckOperationStatus,
)
from hogflow.presentation.models import (
    ConfirmationKind,
    ConfirmationRequest,
    CountingLanePanel,
    DockPanel,
    OperatorActionState,
    OperatorScreen,
    OperatorStatus,
    TotalsPanel,
)
from hogflow.presentation.ports import OperatorView


class OperatorPresenter:
    """Delegate commands and render only fresh Phase 8 snapshots."""

    def __init__(self, application: OperatorApplication, view: OperatorView) -> None:
        self._application = application
        self._view = view

    def refresh(self, dock_id: DockId = DockId.DOCK_1) -> OperatorScreen:
        """Manually refresh one selected dock from the current runtime snapshot."""

        snapshot = self._application.snapshot()
        status = (
            OperatorStatus.LANE_OCCUPIED
            if snapshot.counting_lane.occupied
            else OperatorStatus.READY
        )
        return self._render(snapshot, dock_id, status)

    def register_truck(self, command: RegisterTruckCommand) -> OperatorScreen:
        """Register one truck and render its selected dock."""

        return self._perform(
            lambda: self._application.register_truck(command),
            command.dock_id,
            OperatorStatus.TRUCK_REGISTERED,
        )

    def start_truck(self, dock_id: DockId) -> OperatorScreen:
        """Start one truck and render explicit operator feedback."""

        return self._perform(
            lambda: self._application.start_truck(dock_id),
            dock_id,
            OperatorStatus.TRUCK_STARTED,
        )

    def start_session(self, dock_id: DockId, session_id: str) -> OperatorScreen:
        """Start one unloading session and expose shared-lane ownership."""

        return self._perform(
            lambda: self._application.start_session(dock_id, session_id),
            dock_id,
            OperatorStatus.SESSION_STARTED,
        )

    def complete_session(self, dock_id: DockId) -> OperatorScreen:
        """Complete the lane-owning session and render its finalized total."""

        return self._perform(
            lambda: self._application.complete_session(dock_id),
            dock_id,
            OperatorStatus.SESSION_COMPLETED,
        )

    def cancel_session(self, dock_id: DockId) -> OperatorScreen:
        """Require confirmation before discarding one unfinished live count."""

        snapshot = self._application.snapshot()
        lane = snapshot.counting_lane
        if not lane.occupied or lane.active_dock_id is not dock_id:
            return self._perform(
                lambda: self._application.cancel_session(dock_id),
                dock_id,
                OperatorStatus.SESSION_CANCELLED,
            )
        request = ConfirmationRequest(
            kind=ConfirmationKind.CANCEL_SESSION,
            title="Cancel unloading session?",
            message=(
                f"Cancel {lane.active_session_id} at {_dock_label(dock_id)}. "
                f"The unfinished live count ({lane.current_session_count}) will be "
                "discarded; completed earlier sessions remain unchanged."
            ),
        )
        if not self._view.confirm(request):
            return self._render(snapshot, dock_id, OperatorStatus.ACTION_NOT_CONFIRMED)
        return self._perform(
            lambda: self._application.cancel_session(dock_id),
            dock_id,
            OperatorStatus.SESSION_CANCELLED,
        )

    def complete_truck(self, dock_id: DockId) -> OperatorScreen:
        """Complete one eligible operation through the application boundary."""

        return self._perform(
            lambda: self._application.complete_truck(dock_id),
            dock_id,
            OperatorStatus.TRUCK_COMPLETED,
        )

    def cancel_truck(self, dock_id: DockId) -> OperatorScreen:
        """Require confirmation before cancelling a truck operation."""

        snapshot = self._application.snapshot()
        dock = snapshot.for_dock(dock_id)
        if dock.operation_id is None or dock.operation_status is None:
            return self._perform(
                lambda: self._application.cancel_truck(dock_id),
                dock_id,
                OperatorStatus.OPERATION_CANCELLED,
            )
        lane = snapshot.counting_lane
        discards_live_count = lane.occupied and lane.active_dock_id is dock_id
        live_text = (
            f" Its active session will be cancelled and unfinished live count "
            f"({lane.current_session_count}) discarded."
            if discards_live_count
            else ""
        )
        request = ConfirmationRequest(
            kind=ConfirmationKind.CANCEL_TRUCK,
            title="Cancel truck operation?",
            message=(
                f"Cancel operation {dock.operation_id} at {_dock_label(dock_id)}."
                f"{live_text} Completed session totals remain unchanged."
            ),
        )
        if not self._view.confirm(request):
            return self._render(snapshot, dock_id, OperatorStatus.ACTION_NOT_CONFIRMED)
        return self._perform(
            lambda: self._application.cancel_truck(dock_id),
            dock_id,
            OperatorStatus.OPERATION_CANCELLED,
        )

    def request_exit(self, dock_id: DockId = DockId.DOCK_1) -> bool:
        """Confirm risky shutdown, close Phase 8 resources, then close the view."""

        snapshot = self._application.snapshot()
        if _requires_exit_confirmation(snapshot):
            request = _exit_confirmation(snapshot)
            if not self._view.confirm(request):
                self._render(snapshot, dock_id, OperatorStatus.ACTION_NOT_CONFIRMED)
                return False
        try:
            closed = self._application.shutdown()
            self._render(closed, dock_id, OperatorStatus.APPLICATION_CLOSED)
        except ExpectedOperatorError as exc:
            self._view.show_error(str(exc))
            raise
        self._view.close()
        return True

    def _perform(
        self,
        action: Callable[[], MultiDockRuntimeSnapshot],
        dock_id: DockId,
        status: OperatorStatus,
    ) -> OperatorScreen:
        try:
            snapshot = action()
            return self._render(snapshot, dock_id, status)
        except ExpectedOperatorError as exc:
            self._view.show_error(str(exc))
            raise

    def _render(
        self,
        snapshot: MultiDockRuntimeSnapshot,
        dock_id: DockId,
        status: OperatorStatus,
    ) -> OperatorScreen:
        screen = screen_from_snapshot(snapshot, dock_id=dock_id, status=status)
        self._view.render(screen)
        return screen


def screen_from_snapshot(
    snapshot: MultiDockRuntimeSnapshot,
    *,
    dock_id: DockId = DockId.DOCK_1,
    status: OperatorStatus | None = None,
) -> OperatorScreen:
    """Create a transient workflow-safe display projection from one snapshot."""

    selected_dock = DockId.parse(dock_id)
    lane = snapshot.counting_lane
    active_dock = None if lane.active_dock_id is None else snapshot.for_dock(lane.active_dock_id)
    lane_status = "Closed" if lane.closed else ("Occupied" if lane.occupied else "Idle")
    lane_panel = CountingLanePanel(
        status=lane_status,
        current_dock=_dock_label(lane.active_dock_id),
        truck=_text(lane.active_operation_id),
        pig_type=_pig_type_label(None if active_dock is None else active_dock.active_pig_type),
        current_session=_text(lane.active_session_id),
        live_count=lane.current_session_count,
    )
    dock_panels = tuple(
        DockPanel(
            dock_id=item.dock_id.value,
            title=_dock_label(item.dock_id),
            operation_id=_text(item.operation_id),
            status=item.runtime_status.value.replace("_", " ").title(),
            pig_type=_pig_type_label(item.active_pig_type or item.next_planned_pig_type),
            truck_total=item.truck_total,
            current_session=_text(item.active_session_id),
            next_session=_text(item.next_planned_session_id),
            next_pig_type=_pig_type_label(item.next_planned_pig_type),
            is_selected=item.dock_id is selected_dock,
            owns_lane=lane.occupied and lane.active_dock_id is item.dock_id,
        )
        for item in snapshot.dock_snapshots
    )
    totals = TotalsPanel(
        total_pigs=snapshot.aggregate_completed_pig_count,
        totals_by_pig_type=tuple(
            (_pig_type_label(item.pig_type), item.actual_count)
            for item in snapshot.aggregate_totals_by_pig_type
        ),
        completed_trucks=snapshot.completed_operation_count,
        active_trucks=snapshot.active_operation_count,
    )
    current_status = status or (
        OperatorStatus.LANE_OCCUPIED if lane.occupied else OperatorStatus.READY
    )
    return OperatorScreen(
        counting_lane=lane_panel,
        docks=dock_panels,
        totals=totals,
        selected_dock_id=selected_dock.value,
        actions=_action_state(snapshot, selected_dock),
        status_message=current_status.value,
        generated_at=snapshot.generated_at.isoformat(),
    )


def _action_state(
    snapshot: MultiDockRuntimeSnapshot,
    selected_dock: DockId,
) -> OperatorActionState:
    dock = snapshot.for_dock(selected_dock)
    runtime_open = not snapshot.coordinator_closed
    owns_lane = (
        runtime_open
        and snapshot.counting_lane.occupied
        and snapshot.counting_lane.active_dock_id is selected_dock
    )
    return OperatorActionState(
        register_truck=runtime_open and dock.available,
        start_truck=runtime_open and dock.runtime_status is DockRuntimeStatus.PLANNED,
        start_session=runtime_open and dock.operation_can_start_session,
        complete_session=owns_lane,
        cancel_session=owns_lane,
        complete_truck=runtime_open and dock.operation_can_complete,
        cancel_truck=runtime_open
        and dock.operation_status in (TruckOperationStatus.PLANNED, TruckOperationStatus.ACTIVE),
        refresh=True,
        exit=True,
    )


def _requires_exit_confirmation(snapshot: MultiDockRuntimeSnapshot) -> bool:
    return snapshot.counting_lane.occupied or snapshot.occupied_dock_count > 0


def _exit_confirmation(snapshot: MultiDockRuntimeSnapshot) -> ConfirmationRequest:
    lane = snapshot.counting_lane
    if lane.occupied:
        detail = (
            f"The active session {lane.active_session_id} at "
            f"{_dock_label(lane.active_dock_id)} will be cancelled and unfinished live "
            f"count ({lane.current_session_count}) discarded. The truck will remain unfinished."
        )
    else:
        detail = (
            "One or more planned or active truck operations exist. They are in-memory only "
            "and will not be persisted when the application exits."
        )
    return ConfirmationRequest(
        kind=ConfirmationKind.EXIT_ACTIVE_RUNTIME,
        title="Exit HogFlow?",
        message=f"{detail} Close the shared counting runtime and exit?",
    )


def _dock_label(dock_id: DockId | None) -> str:
    if dock_id is None:
        return "—"
    return f"Dock {dock_id.sequence_number}"


def _pig_type_label(pig_type: PigType | None) -> str:
    if pig_type is None:
        return "—"
    if pig_type is PigType.P12:
        return "P-12"
    return pig_type.value.upper()


def _text(value: str | None) -> str:
    return "—" if value is None else value


__all__ = ["OperatorPresenter", "screen_from_snapshot"]
