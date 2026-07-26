"""Expected failures for the shared Phase 8.4 counting-lane resource."""

from hogflow.core import HogFlowError


class SharedCountingLaneError(HogFlowError):
    """Base class for expected shared counting-lane failures."""


class CountingLaneConfigurationError(SharedCountingLaneError):
    """Raised when the shared source or counter cannot be configured safely."""


class CountingLaneOccupiedError(SharedCountingLaneError):
    """Raised when another unloading session already owns the shared lane."""


class CountingLaneNotBoundError(SharedCountingLaneError):
    """Raised when a command requires an active session binding."""


class CountingLaneOwnershipError(SharedCountingLaneError):
    """Raised when a dock attempts to use another dock's active binding."""


class CountingLaneClosedError(SharedCountingLaneError):
    """Raised when a command targets a closed shared counting lane."""


class CountingLaneTransitionError(SharedCountingLaneError):
    """Raised when the lane cannot commit a lifecycle transition safely."""


class CountingLaneShutdownError(SharedCountingLaneError):
    """Raised when the shared counter cannot close safely."""


__all__ = [
    "CountingLaneClosedError",
    "CountingLaneConfigurationError",
    "CountingLaneNotBoundError",
    "CountingLaneOccupiedError",
    "CountingLaneOwnershipError",
    "CountingLaneShutdownError",
    "CountingLaneTransitionError",
    "SharedCountingLaneError",
]
