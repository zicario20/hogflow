"""Framework-independent finite-video and live tracking boundaries."""

from hogflow.tracking.config import (
    ByteTrackConfiguration,
    byte_track_configuration_fingerprint,
)
from hogflow.tracking.contracts import Tracker
from hogflow.tracking.errors import (
    FatalTrackingError,
    MalformedTrackerOutputError,
    StaleTrackingRequestError,
    TemporaryTrackingError,
    TrackerCloseError,
    TrackerInitializationError,
    TrackerLifecycleError,
    TrackerResetError,
    TrackingError,
    TrackingPreviewError,
)
from hogflow.tracking.fakes import (
    DeterministicIoUTracker,
    EmptyTracker,
    FailingTracker,
    ScriptedTracker,
    SlowTracker,
    synthetic_tracked_object,
)
from hogflow.tracking.models import (
    LiveTrackingRunSummary,
    LiveTrackingSnapshot,
    LiveTrackingStats,
    TrackedObject,
    TrackerMetadata,
    TrackingErrorCategory,
    TrackingHealthState,
    TrackingRequest,
    TrackingResult,
    TrackState,
)
from hogflow.tracking.ports import LiveTracker, TrackingPreview
from hogflow.tracking.telemetry import LiveTrackingTelemetry

__all__ = [
    "ByteTrackConfiguration",
    "DeterministicIoUTracker",
    "EmptyTracker",
    "FailingTracker",
    "FatalTrackingError",
    "LiveTracker",
    "LiveTrackingRunSummary",
    "LiveTrackingSnapshot",
    "LiveTrackingStats",
    "LiveTrackingTelemetry",
    "MalformedTrackerOutputError",
    "ScriptedTracker",
    "SlowTracker",
    "StaleTrackingRequestError",
    "TemporaryTrackingError",
    "TrackState",
    "TrackedObject",
    "Tracker",
    "TrackerCloseError",
    "TrackerInitializationError",
    "TrackerLifecycleError",
    "TrackerMetadata",
    "TrackerResetError",
    "TrackingError",
    "TrackingErrorCategory",
    "TrackingHealthState",
    "TrackingPreview",
    "TrackingPreviewError",
    "TrackingRequest",
    "TrackingResult",
    "byte_track_configuration_fingerprint",
    "synthetic_tracked_object",
]
