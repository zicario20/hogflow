"""Snapshot-driven presenter for the Phase 9.1 operator workflow."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from hogflow.application import (
    DockId,
    ExpectedOperatorError,
    MultiDockRuntimeSnapshot,
    OperatorApplication,
    PigType,
    RegisterTruckCommand,
)
from hogflow.presentation.models import (
    CountingLanePanel,
    DockPanel,
    OperatorScreen,
    TotalsPanel,
)
from hogflow.presentation.ports import OperatorView

T = TypeVar("T")


class OperatorPresenter:
    """Delegate commands and render only fresh Phase 8 snapshots."""

    def __init__(self, application: OperatorApplication, view: OperatorView) -> None:
        self._application = application
        self._view = view

    def refresh(self) -> OperatorScreen:
        """Manually refresh from the coordinator-backed application snapshot."""

        return self._perform(self._application.snapshot)

    def register_truck(self, command: RegisterTruckCommand) -> OperatorScreen:
        """Register one truck and refresh."""

        return self._perform(lambda: self._application.register_truck(command))

    def start_truck(self, dock_id: DockId) -> OperatorScreen:
        """Start one truck and refresh."""

        return self._perform(lambda: self._application.start_truck(dock_id))

    def start_session(self, dock_id: DockId, session_id: str) -> OperatorScreen:
        """Start one unloading session and refresh."""

        return self._perform(lambda: self._application.start_session(dock_id, session_id))

    def complete_session(self, dock_id: DockId) -> OperatorScreen:
        """Complete the lane-owning session and refresh."""

        return self._perform(lambda: self._application.complete_session(dock_id))

    def cancel_session(self, dock_id: DockId) -> OperatorScreen:
        """Cancel the lane-owning session and refresh."""

        return self._perform(lambda: self._application.cancel_session(dock_id))

    def complete_truck(self, dock_id: DockId) -> OperatorScreen:
        """Complete one eligible truck and refresh."""

        return self._perform(lambda: self._application.complete_truck(dock_id))

    def cancel_truck(self, dock_id: DockId) -> OperatorScreen:
        """Cancel one truck and refresh."""

        return self._perform(lambda: self._application.cancel_truck(dock_id))

    def _perform(
        self,
        action: Callable[[], MultiDockRuntimeSnapshot],
    ) -> OperatorScreen:
        try:
            snapshot = action()
            screen = screen_from_snapshot(snapshot)
        except ExpectedOperatorError as exc:
            self._view.show_error(str(exc))
            raise
        self._view.render(screen)
        return screen


def screen_from_snapshot(snapshot: MultiDockRuntimeSnapshot) -> OperatorScreen:
    """Create a transient display projection without storing business state."""

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
            pig_type=_pig_type_label(item.active_pig_type),
            truck_total=item.truck_total,
            current_session=_text(item.active_session_id),
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
    return OperatorScreen(
        counting_lane=lane_panel,
        docks=dock_panels,
        totals=totals,
        generated_at=snapshot.generated_at.isoformat(),
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
