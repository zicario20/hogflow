"""Public application protocol consumed by the operator presentation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hogflow.application.models import RegisterTruckCommand
from hogflow.domain import DockId
from hogflow.sessions import MultiDockRuntimeSnapshot


@runtime_checkable
class OperatorApplication(Protocol):
    """Operator commands over the public Phase 8 runtime coordinator."""

    def snapshot(self) -> MultiDockRuntimeSnapshot:
        """Return the current immutable runtime snapshot."""

    def register_truck(self, command: RegisterTruckCommand) -> MultiDockRuntimeSnapshot:
        """Register one planned operation and return a fresh snapshot."""

    def start_truck(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Start one planned truck operation."""

    def start_session(self, dock_id: DockId, session_id: str) -> MultiDockRuntimeSnapshot:
        """Start one unloading session using a fresh crossing lifecycle."""

    def complete_session(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Finalize the lane count into the active unloading session."""

    def cancel_session(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Cancel the active unloading session and discard its live count."""

    def complete_truck(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Complete one eligible truck operation."""

    def cancel_truck(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Cancel one truck operation."""

    def shutdown(self) -> MultiDockRuntimeSnapshot:
        """Close the shared runtime safely and return its terminal snapshot."""


__all__ = ["OperatorApplication"]
