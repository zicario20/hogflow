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
    """Raised when source ownership is invalid or conflicts across docks."""


class DockLifecycleConflictError(MultiDockRuntimeError):
    """Raised when lifecycle provenance conflicts across dock runtimes."""


class DockOperationMismatchError(MultiDockRuntimeError):
    """Raised when an operation does not belong to the requested dock."""


class DockSessionNotActiveError(MultiDockRuntimeError):
    """Raised when a command requires an active dock session lifecycle."""


class DockRuntimeTransitionError(MultiDockRuntimeError):
    """Raised when a dock-local runtime transition cannot commit safely."""


class MultiDockShutdownError(MultiDockRuntimeError):
    """Raised after shutdown attempts every dock but one or more closes fail."""

    def __init__(
        self,
        *,
        closed_dock_values: tuple[str, ...],
        failed_dock_values: tuple[str, ...],
    ) -> None:
        self.closed_dock_values = closed_dock_values
        self.failed_dock_values = failed_dock_values
        failed = ", ".join(failed_dock_values)
        super().__init__(f"Multi-dock shutdown could not close: {failed}.")


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
