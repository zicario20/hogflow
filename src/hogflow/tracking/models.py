"""Immutable framework-neutral models for live multi-object tracking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from re import fullmatch

from hogflow.core import InputDataError
from hogflow.detection.inference import LiveDetectionRunSummary, LiveDetectionStats
from hogflow.models import Detection, Track

_OPAQUE_ID = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
_SOURCE_ID = r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}"
_SHA256 = r"[0-9a-f]{64}"


def _non_negative_integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InputDataError(f"{name} must be a non-negative integer.")
    return value


def _positive_integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InputDataError(f"{name} must be a positive integer.")
    return value


def _non_negative_number(value: object, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or float(value) < 0
    ):
        raise InputDataError(f"{name} must be a finite non-negative number.")
    return float(value)


def _aware_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InputDataError(f"{name} must be a timezone-aware datetime.")
    return value


class TrackState(str, Enum):
    """Truthful state exposed for objects associated with the current frame."""

    VISIBLE = "visible"


class TrackingHealthState(str, Enum):
    """Bounded lifecycle states for one live tracker instance."""

    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPING = "stopping"
    STOPPED = "stopped"


class TrackingErrorCategory(str, Enum):
    """Sanitized tracking error categories without exception text."""

    NONE = "none"
    INITIALIZATION = "initialization"
    INPUT = "input"
    STALE = "stale"
    UPDATE = "update"
    OUTPUT = "output"
    RESET = "reset"
    CLOSE = "close"


@dataclass(frozen=True, slots=True)
class TrackingRequest:
    """Detections from exactly one stream frame submitted to a tracker."""

    source_id: str
    frame_sequence: int
    captured_at: datetime
    frame_width: int
    frame_height: int
    detections: tuple[Detection, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or fullmatch(_SOURCE_ID, self.source_id) is None:
            raise InputDataError("Tracking source ID must be opaque text.")
        _non_negative_integer(self.frame_sequence, "Tracking frame sequence")
        _aware_datetime(self.captured_at, "Tracking capture time")
        _positive_integer(self.frame_width, "Tracking frame width")
        _positive_integer(self.frame_height, "Tracking frame height")
        if not isinstance(self.detections, tuple) or not all(
            isinstance(item, Detection) for item in self.detections
        ):
            raise InputDataError("Tracking detections must be an immutable Detection tuple.")
        for detection in self.detections:
            box = detection.bounding_box
            if (
                box.x_min < 0
                or box.y_min < 0
                or box.x_max > self.frame_width
                or box.y_max > self.frame_height
            ):
                raise InputDataError("Tracking detections must remain within the source frame.")


@dataclass(frozen=True, slots=True)
class TrackedObject:
    """One current visible association using the canonical immutable ``Track``.

    Optional age/hit/miss values remain ``None`` when an adapter cannot expose
    them truthfully. A track ID is temporary and scoped to one tracker lifecycle.
    """

    track: Track
    source_detection_index: int | None = None
    state: TrackState = TrackState.VISIBLE
    age_frames: int | None = None
    hits: int | None = None
    missed_frames: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.track, Track):
            raise InputDataError("Tracked object must contain a canonical Track.")
        if self.source_detection_index is not None:
            _non_negative_integer(self.source_detection_index, "Source detection index")
        if not isinstance(self.state, TrackState):
            raise InputDataError("Tracked object state must be explicit.")
        for name in ("age_frames", "hits", "missed_frames"):
            value = getattr(self, name)
            if value is not None:
                _non_negative_integer(value, name)


@dataclass(frozen=True, slots=True)
class TrackerMetadata:
    """Sanitized identity and configuration provenance for one tracker."""

    tracker_id: str
    framework: str
    framework_version: str
    configuration_fingerprint: str
    current_results_only: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.tracker_id, str) or fullmatch(_OPAQUE_ID, self.tracker_id) is None:
            raise InputDataError("Tracker ID must be a non-sensitive opaque identifier.")
        for name in ("framework", "framework_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InputDataError(f"{name} must be non-empty text.")
        if fullmatch(_SHA256, self.configuration_fingerprint) is None:
            raise InputDataError("Tracker configuration fingerprint must be SHA-256 text.")
        if not isinstance(self.current_results_only, bool):
            raise InputDataError("Tracker result semantics must be boolean.")


@dataclass(frozen=True, slots=True)
class TrackingResult:
    """Tracked objects associated with exactly one detection frame."""

    source_id: str
    frame_sequence: int
    captured_at: datetime
    frame_width: int
    frame_height: int
    tracked_objects: tuple[TrackedObject, ...]
    tracker_id: str
    tracker_version: str
    configuration_fingerprint: str
    processing_started_at: datetime
    processing_finished_at: datetime
    tracking_latency_ms: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or fullmatch(_SOURCE_ID, self.source_id) is None:
            raise InputDataError("Tracking result source ID must be opaque text.")
        _non_negative_integer(self.frame_sequence, "Tracking result frame sequence")
        _aware_datetime(self.captured_at, "Tracking result capture time")
        _positive_integer(self.frame_width, "Tracking result frame width")
        _positive_integer(self.frame_height, "Tracking result frame height")
        if not isinstance(self.tracked_objects, tuple) or not all(
            isinstance(item, TrackedObject) for item in self.tracked_objects
        ):
            raise InputDataError("Tracking result objects must be an immutable tuple.")
        for tracked_object in self.tracked_objects:
            box = tracked_object.track.detection.bounding_box
            if (
                box.x_min < 0
                or box.y_min < 0
                or box.x_max > self.frame_width
                or box.y_max > self.frame_height
            ):
                raise InputDataError("Tracked boxes must remain within the source frame.")
        if not isinstance(self.tracker_id, str) or fullmatch(_OPAQUE_ID, self.tracker_id) is None:
            raise InputDataError("Tracking result tracker ID must be opaque text.")
        if not isinstance(self.tracker_version, str) or not self.tracker_version.strip():
            raise InputDataError("Tracking result tracker version must be non-empty text.")
        if fullmatch(_SHA256, self.configuration_fingerprint) is None:
            raise InputDataError("Tracking result configuration fingerprint must be SHA-256 text.")
        _aware_datetime(self.processing_started_at, "Tracking start time")
        _aware_datetime(self.processing_finished_at, "Tracking finish time")
        if self.processing_finished_at < self.processing_started_at:
            raise InputDataError("Tracking completion cannot precede its start.")
        object.__setattr__(
            self,
            "tracking_latency_ms",
            _non_negative_number(self.tracking_latency_ms, "Tracking latency"),
        )


@dataclass(frozen=True, slots=True)
class LiveTrackingStats:
    """Bounded aggregate telemetry for one live tracker lifecycle.

    Track-volume fields are diagnostics only. They are not pig counts and do
    not represent unique animals.
    """

    tracking_requests: int
    tracking_successes: int
    tracking_failures: int
    lifecycle_failures: int
    zero_detection_updates: int
    tracks_emitted: int
    active_tracks_current: int
    active_tracks_peak: int
    frames_with_tracks: int
    frames_without_tracks: int
    tracker_resets: int
    tracker_restarts: int
    tracker_closes: int
    stale_requests_rejected: int
    malformed_detections_rejected: int
    preview_failures: int
    total_tracking_latency_ms: float
    last_tracking_latency_ms: float
    average_tracking_latency_ms: float
    maximum_tracking_latency_ms: float
    last_tracking_frame_id: int | None
    last_tracking_error: TrackingErrorCategory
    current_health_state: TrackingHealthState

    def __post_init__(self) -> None:
        for name in (
            "tracking_requests",
            "tracking_successes",
            "tracking_failures",
            "lifecycle_failures",
            "zero_detection_updates",
            "tracks_emitted",
            "active_tracks_current",
            "active_tracks_peak",
            "frames_with_tracks",
            "frames_without_tracks",
            "tracker_resets",
            "tracker_restarts",
            "tracker_closes",
            "stale_requests_rejected",
            "malformed_detections_rejected",
            "preview_failures",
        ):
            _non_negative_integer(getattr(self, name), name)
        for name in (
            "total_tracking_latency_ms",
            "last_tracking_latency_ms",
            "average_tracking_latency_ms",
            "maximum_tracking_latency_ms",
        ):
            _non_negative_number(getattr(self, name), name)
        if self.last_tracking_frame_id is not None:
            _non_negative_integer(self.last_tracking_frame_id, "Last tracking frame ID")
        if not isinstance(self.last_tracking_error, TrackingErrorCategory):
            raise InputDataError("Last tracking error category must be explicit.")
        if not isinstance(self.current_health_state, TrackingHealthState):
            raise InputDataError("Tracking health state must be explicit.")
        if self.tracking_requests != self.tracking_successes + self.tracking_failures:
            raise InputDataError("Tracking accounting requires requests = successes + failures.")


@dataclass(frozen=True, slots=True)
class LiveTrackingRunSummary:
    """Terminal detector and tracker state for one sanitized live run."""

    detection_summary: LiveDetectionRunSummary
    tracker: TrackerMetadata
    tracking_statistics: LiveTrackingStats
    tracker_closed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.detection_summary, LiveDetectionRunSummary):
            raise InputDataError("Live tracking summary requires a detection summary.")
        if not isinstance(self.tracker, TrackerMetadata):
            raise InputDataError("Live tracking summary tracker metadata is invalid.")
        if not isinstance(self.tracking_statistics, LiveTrackingStats):
            raise InputDataError("Live tracking summary statistics are invalid.")
        if not isinstance(self.tracker_closed, bool):
            raise InputDataError("Live tracking summary close state must be boolean.")


@dataclass(frozen=True, slots=True)
class LiveTrackingSnapshot:
    """Current detector and tracker telemetry forwarded without frame history."""

    detection: LiveDetectionStats
    tracking: LiveTrackingStats


__all__ = [
    "LiveTrackingRunSummary",
    "LiveTrackingSnapshot",
    "LiveTrackingStats",
    "TrackState",
    "TrackedObject",
    "TrackerMetadata",
    "TrackingErrorCategory",
    "TrackingHealthState",
    "TrackingRequest",
    "TrackingResult",
]
