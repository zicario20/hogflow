"""Expected framework-neutral failures for live multi-object tracking."""

from hogflow.core import HogFlowError


class TrackingError(HogFlowError):
    """Base class for expected live-tracking failures."""


class TrackerInitializationError(TrackingError):
    """Raised when a tracker cannot initialize its runtime resources."""


class TrackerLifecycleError(TrackingError):
    """Raised when a tracker operation conflicts with its lifecycle state."""


class TemporaryTrackingError(TrackingError):
    """Raised when one tracker update fails but later updates may continue."""


class FatalTrackingError(TrackingError):
    """Raised when tracker state can no longer be used safely."""


class StaleTrackingRequestError(TrackingError):
    """Raised when a request is not newer than the last accepted frame."""


class MalformedTrackerOutputError(FatalTrackingError):
    """Raised when framework output cannot become valid HogFlow tracks."""


class TrackerResetError(FatalTrackingError):
    """Raised when tracker state cannot be reset safely."""


class TrackerCloseError(FatalTrackingError):
    """Raised when tracker resource cleanup fails."""


class TrackingPreviewError(TrackingError):
    """Raised for an expected local tracking-preview failure."""


__all__ = [
    "FatalTrackingError",
    "MalformedTrackerOutputError",
    "StaleTrackingRequestError",
    "TemporaryTrackingError",
    "TrackerCloseError",
    "TrackerInitializationError",
    "TrackerLifecycleError",
    "TrackerResetError",
    "TrackingError",
    "TrackingPreviewError",
]
