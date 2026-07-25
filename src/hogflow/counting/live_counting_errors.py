"""Expected framework-neutral failures for lifecycle directional counting."""

from hogflow.core import HogFlowError


class LiveCountingError(HogFlowError):
    """Base class for expected live counting failures."""


class CountingLifecycleError(LiveCountingError):
    """Raised when counting work conflicts with its active lifecycle."""


class StaleCountingRequestError(LiveCountingError):
    """Raised when a crossing result is not newer than the last accepted frame."""


class DuplicateCountingEventIdentityError(LiveCountingError):
    """Raised when one temporary track has multiple events in one frame."""


class CrossingCountingMismatchError(LiveCountingError):
    """Raised when crossing provenance does not match counting configuration."""


class CountingCapacityError(LiveCountingError):
    """Raised before the bounded counted-identity capacity would be exceeded."""


class CountingPreviewError(LiveCountingError):
    """Raised for an expected local counting-preview failure."""


__all__ = [
    "CountingCapacityError",
    "CountingLifecycleError",
    "CountingPreviewError",
    "CrossingCountingMismatchError",
    "DuplicateCountingEventIdentityError",
    "LiveCountingError",
    "StaleCountingRequestError",
]
