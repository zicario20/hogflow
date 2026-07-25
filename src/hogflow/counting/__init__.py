"""Counting primitives for HogFlow experiments."""

from hogflow.counting.line_crossing import (
    CrossingDirection,
    CrossingEvent,
    DirectionalLineCounter,
    Line,
    Point,
)
from hogflow.counting.live_crossing import (
    VirtualLineCrossingDetector,
    representative_point,
)
from hogflow.counting.live_errors import (
    CrossingLifecycleError,
    CrossingPreviewError,
    LiveCrossingError,
    StaleCrossingRequestError,
)
from hogflow.counting.live_models import (
    LineSide,
    LiveCrossingConfiguration,
    LiveCrossingDirection,
    LiveCrossingErrorCategory,
    LiveCrossingEvent,
    LiveCrossingHealthState,
    LiveCrossingResult,
    LiveCrossingRunSummary,
    LiveCrossingSnapshot,
    LiveCrossingStats,
    NormalizedLine,
    NormalizedPoint,
    TrackAnchor,
    TrackCrossingObservation,
)
from hogflow.counting.live_ports import LiveCrossingDetector
from hogflow.counting.live_telemetry import LiveCrossingTelemetry

__all__ = [
    "CrossingLifecycleError",
    "CrossingPreviewError",
    "CrossingDirection",
    "CrossingEvent",
    "DirectionalLineCounter",
    "Line",
    "LineSide",
    "LiveCrossingConfiguration",
    "LiveCrossingDetector",
    "LiveCrossingDirection",
    "LiveCrossingError",
    "LiveCrossingErrorCategory",
    "LiveCrossingEvent",
    "LiveCrossingHealthState",
    "LiveCrossingResult",
    "LiveCrossingRunSummary",
    "LiveCrossingSnapshot",
    "LiveCrossingStats",
    "LiveCrossingTelemetry",
    "NormalizedLine",
    "NormalizedPoint",
    "Point",
    "StaleCrossingRequestError",
    "TrackAnchor",
    "TrackCrossingObservation",
    "VirtualLineCrossingDetector",
    "representative_point",
]
