"""Expected failures for synchronous multi-dock runtime coordination."""

from __future__ import annotations

from hogflow.core import HogFlowError


class MultiDockRuntimeError(HogFlowError):
    """Base class for expected Phase 8.3 coordination failures."""


class DockRuntimeConfigurationError(MultiDockRuntimeError):
    """Raised when a dock runtime cannot be configured safely."""


class DockRuntimeNotFoundError(MultiDockRuntimeError):
    """Raised when a requested dock has no current runtime."""


class DockRuntimeOccupiedError(MultiDockRuntimeError):
    """Raised when a non-terminal runtime already occupies a dock."""


class DockRuntimeClosedError(MultiDockRuntimeError):
    """Raised when a command targets a closed coordinator."""


class DockSourceConflictError(MultiDockRuntimeError):
    """Raised when an input does not belong to the shared counting source."""


class DockLifecycleConflictError(MultiDockRuntimeError):
    """Raised when lifecycle provenance conflicts with the shared lane."""


class DockOperationMismatchError(MultiDockRuntimeError):
    """Raised when an operation does not belong to the requested dock."""


class DockSessionNotActiveError(MultiDockRuntimeError):
    """Raised when a command requires an active dock session lifecycle."""


class DockRuntimeTransitionError(MultiDockRuntimeError):
    """Raised when a dock-local runtime transition cannot commit safely."""


class MultiDockShutdownError(MultiDockRuntimeError):
    """Raised when the one shared counting resource cannot close."""

    def __init__(self, *, bound_dock_value: str | None) -> None:
        self.bound_dock_value = bound_dock_value
        suffix = "" if bound_dock_value is None else f" while bound to {bound_dock_value}"
        super().__init__(f"Shared counting lane could not close{suffix}.")


__all__ = [
    "DockLifecycleConflictError",
    "DockOperationMismatchError",
    "DockRuntimeClosedError",
    "DockRuntimeConfigurationError",
    "DockRuntimeNotFoundError",
    "DockRuntimeOccupiedError",
    "DockRuntimeTransitionError",
    "DockSessionNotActiveError",
    "DockSourceConflictError",
    "MultiDockRuntimeError",
    "MultiDockShutdownError",
]
