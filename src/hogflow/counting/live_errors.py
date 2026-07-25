"""Expected framework-neutral failures for live virtual-line crossing."""

from hogflow.core import HogFlowError


class LiveCrossingError(HogFlowError):
    """Base class for expected live crossing failures."""


class CrossingLifecycleError(LiveCrossingError):
    """Raised when crossing work conflicts with the detector lifecycle."""


class StaleCrossingRequestError(LiveCrossingError):
    """Raised when a tracking result is not newer than the last accepted frame."""


class CrossingPreviewError(LiveCrossingError):
    """Raised for an expected local crossing-preview failure."""


__all__ = [
    "CrossingLifecycleError",
    "CrossingPreviewError",
    "LiveCrossingError",
    "StaleCrossingRequestError",
]
