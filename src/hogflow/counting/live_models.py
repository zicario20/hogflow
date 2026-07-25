"""Immutable framework-neutral models for live virtual-line crossing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import hypot, isfinite
from re import fullmatch

from hogflow.core import ConfigurationError, InputDataError
from hogflow.tracking.models import LiveTrackingRunSummary, LiveTrackingSnapshot

_SOURCE_ID = r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}"
_OPAQUE_ID = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
_SHA256 = r"[0-9a-f]{64}"
_SEGMENT_INTERSECTION_TOLERANCE = 1e-12


def _unit_coordinate(value: object, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or not 0.0 <= float(value) <= 1.0
    ):
        raise InputDataError(f"{name} must be a finite number from 0 through 1.")
    return float(value)


def _non_negative_integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InputDataError(f"{name} must be a non-negative integer.")
    return value


def _aware_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InputDataError(f"{name} must be a timezone-aware datetime.")
    return value


class LineSide(str, Enum):
    """Explicit side of an oriented virtual line."""

    NEGATIVE = "negative"
    ON_LINE = "on_line"
    POSITIVE = "positive"


class LiveCrossingDirection(str, Enum):
    """Neutral geometric transition across an oriented virtual line."""

    NEGATIVE_TO_POSITIVE = "negative_to_positive"
    POSITIVE_TO_NEGATIVE = "positive_to_negative"


class TrackAnchor(str, Enum):
    """Supported representative-point policies for one tracked box."""

    BOTTOM_CENTER = "bottom_center"
    CENTER = "center"


class LiveCrossingHealthState(str, Enum):
    """Bounded lifecycle states for one live crossing detector."""

    CREATED = "created"
    RUNNING = "running"
    FAILED = "failed"
    STOPPED = "stopped"


class LiveCrossingErrorCategory(str, Enum):
    """Sanitized live crossing error categories."""

    NONE = "none"
    CONFIGURATION = "configuration"
    INPUT = "input"
    LIFECYCLE = "lifecycle"
    STALE = "stale"
    PREVIEW = "preview"


@dataclass(frozen=True, slots=True)
class NormalizedPoint:
    """A finite image point independent of frame resolution."""

    x: float
    y: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _unit_coordinate(self.x, "Normalized x"))
        object.__setattr__(self, "y", _unit_coordinate(self.y, "Normalized y"))


@dataclass(frozen=True, slots=True)
class NormalizedLine:
    """A finite oriented segment whose endpoint order defines side signs."""

    start: NormalizedPoint
    end: NormalizedPoint

    def __post_init__(self) -> None:
        if not isinstance(self.start, NormalizedPoint) or not isinstance(self.end, NormalizedPoint):
            raise InputDataError("Normalized line endpoints must be NormalizedPoint values.")
        if self.start == self.end:
            raise InputDataError("Normalized line endpoints must be different.")

    def side_value(self, point: NormalizedPoint) -> float:
        """Return the signed 2D orientation cross product."""

        if not isinstance(point, NormalizedPoint):
            raise InputDataError("Line classification requires a NormalizedPoint.")
        line_x = self.end.x - self.start.x
        line_y = self.end.y - self.start.y
        point_x = point.x - self.start.x
        point_y = point.y - self.start.y
        return line_x * point_y - line_y * point_x

    def signed_distance(self, point: NormalizedPoint) -> float:
        """Return signed perpendicular distance in normalized image units."""

        length = hypot(self.end.x - self.start.x, self.end.y - self.start.y)
        return self.side_value(point) / length

    def classify(self, point: NormalizedPoint, epsilon: float) -> LineSide:
        """Classify a point using an explicit perpendicular-distance tolerance."""

        distance = self.signed_distance(point)
        if distance > epsilon:
            return LineSide.POSITIVE
        if distance < -epsilon:
            return LineSide.NEGATIVE
        return LineSide.ON_LINE

    def intersects_movement_segment(
        self,
        previous: NormalizedPoint,
        current: NormalizedPoint,
    ) -> bool:
        """Return whether two real observations span this finite line segment.

        The calculation verifies finite-segment overlap only. It does not
        estimate an intermediate timestamp, frame, trajectory, or crossing
        point.
        """

        return self.movement_intersection_parameter(previous, current) is not None

    def movement_intersection_parameter(
        self,
        previous: NormalizedPoint,
        current: NormalizedPoint,
    ) -> float | None:
        """Return the finite intersection position along this line, if any.

        Zero identifies ``start`` and one identifies ``end``. This geometric
        diagnostic does not estimate a frame, timestamp, or physical path.
        """

        if not isinstance(previous, NormalizedPoint) or not isinstance(current, NormalizedPoint):
            raise InputDataError("Movement intersection requires normalized points.")
        movement_x = current.x - previous.x
        movement_y = current.y - previous.y
        line_x = self.end.x - self.start.x
        line_y = self.end.y - self.start.y
        denominator = movement_x * line_y - movement_y * line_x
        scale = max(hypot(movement_x, movement_y) * hypot(line_x, line_y), 1.0)
        if abs(denominator) <= _SEGMENT_INTERSECTION_TOLERANCE * scale:
            return None
        offset_x = self.start.x - previous.x
        offset_y = self.start.y - previous.y
        movement_parameter = (offset_x * line_y - offset_y * line_x) / denominator
        line_parameter = (offset_x * movement_y - offset_y * movement_x) / denominator
        tolerance = _SEGMENT_INTERSECTION_TOLERANCE
        if (
            -tolerance <= movement_parameter <= 1.0 + tolerance
            and -tolerance <= line_parameter <= 1.0 + tolerance
        ):
            return min(1.0, max(0.0, line_parameter))
        return None


@dataclass(frozen=True, slots=True)
class LiveCrossingConfiguration:
    """Validated optional live crossing policy.

    ``epsilon`` is measured in normalized perpendicular image distance.
    ``absent_track_retention_updates`` counts successful tracking results in
    which an identity is not visible. Crossing is disabled by default.
    """

    enabled: bool = False
    line: NormalizedLine | None = None
    anchor: TrackAnchor = TrackAnchor.BOTTOM_CENTER
    epsilon: float = 0.005
    absent_track_retention_updates: int = 30

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ConfigurationError("Crossing enabled must be boolean.")
        if self.line is not None and not isinstance(self.line, NormalizedLine):
            raise ConfigurationError("Crossing line must be a NormalizedLine.")
        if self.enabled and self.line is None:
            raise ConfigurationError("Enabled crossing requires a normalized line.")
        if not isinstance(self.anchor, TrackAnchor):
            raise ConfigurationError("Crossing anchor policy must be explicit.")
        if (
            not isinstance(self.epsilon, (int, float))
            or isinstance(self.epsilon, bool)
            or not isfinite(self.epsilon)
            or not 0.0 <= float(self.epsilon) <= 1.0
        ):
            raise ConfigurationError("Crossing epsilon must be finite from 0 through 1.")
        object.__setattr__(self, "epsilon", float(self.epsilon))
        if (
            not isinstance(self.absent_track_retention_updates, int)
            or isinstance(self.absent_track_retention_updates, bool)
            or self.absent_track_retention_updates < 0
        ):
            raise ConfigurationError("Absent-track retention must be a non-negative update count.")

    @property
    def fingerprint(self) -> str:
        """Return deterministic configuration provenance without private data."""

        line = self.line
        payload = {
            "absent_track_retention_updates": self.absent_track_retention_updates,
            "anchor": self.anchor.value,
            "enabled": self.enabled,
            "epsilon": self.epsilon,
            "line": (
                None
                if line is None
                else {
                    "end": {"x": line.end.x, "y": line.end.y},
                    "start": {"x": line.start.x, "y": line.start.y},
                }
            ),
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TrackCrossingObservation:
    """One current representative point and its geometric line side."""

    tracker_id: int
    point: NormalizedPoint
    side: LineSide

    def __post_init__(self) -> None:
        _non_negative_integer(self.tracker_id, "Crossing tracker ID")
        if not isinstance(self.point, NormalizedPoint):
            raise InputDataError("Crossing observation point is invalid.")
        if not isinstance(self.side, LineSide):
            raise InputDataError("Crossing observation side must be explicit.")


@dataclass(frozen=True, slots=True)
class LiveCrossingEvent:
    """One observable finite-segment crossing by a temporary track identity."""

    source_id: str
    tracker_lifecycle_id: str
    tracker_id: int
    frame_sequence: int
    previous_frame_sequence: int
    captured_at: datetime
    direction: LiveCrossingDirection
    previous_side: LineSide
    current_side: LineSide
    previous_point: NormalizedPoint
    representative_point: NormalizedPoint
    line_id: str
    configuration_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or fullmatch(_SOURCE_ID, self.source_id) is None:
            raise InputDataError("Crossing event source ID must be opaque text.")
        if (
            not isinstance(self.tracker_lifecycle_id, str)
            or fullmatch(_OPAQUE_ID, self.tracker_lifecycle_id) is None
        ):
            raise InputDataError("Crossing lifecycle ID must be opaque text.")
        _non_negative_integer(self.tracker_id, "Crossing event tracker ID")
        _non_negative_integer(self.frame_sequence, "Crossing event frame sequence")
        _non_negative_integer(
            self.previous_frame_sequence,
            "Previous crossing observation frame sequence",
        )
        if self.previous_frame_sequence >= self.frame_sequence:
            raise InputDataError("Crossing events require increasing observation frames.")
        _aware_datetime(self.captured_at, "Crossing event capture time")
        if not isinstance(self.direction, LiveCrossingDirection):
            raise InputDataError("Crossing event direction must be explicit.")
        if {self.previous_side, self.current_side} != {
            LineSide.NEGATIVE,
            LineSide.POSITIVE,
        }:
            raise InputDataError("Crossing events require opposite stable line sides.")
        expected_direction = (
            LiveCrossingDirection.NEGATIVE_TO_POSITIVE
            if self.previous_side is LineSide.NEGATIVE
            else LiveCrossingDirection.POSITIVE_TO_NEGATIVE
        )
        if self.direction is not expected_direction:
            raise InputDataError("Crossing event direction does not match its side transition.")
        if not isinstance(self.previous_point, NormalizedPoint) or not isinstance(
            self.representative_point, NormalizedPoint
        ):
            raise InputDataError("Crossing event points must be normalized.")
        if not isinstance(self.line_id, str) or fullmatch(_OPAQUE_ID, self.line_id) is None:
            raise InputDataError("Crossing line ID must be opaque text.")
        if fullmatch(_SHA256, self.configuration_fingerprint) is None:
            raise InputDataError("Crossing configuration fingerprint must be SHA-256 text.")


@dataclass(frozen=True, slots=True)
class LiveCrossingResult:
    """Current observations and zero or more crossing events for one frame."""

    source_id: str
    tracker_lifecycle_id: str
    frame_sequence: int
    captured_at: datetime
    observations: tuple[TrackCrossingObservation, ...]
    events: tuple[LiveCrossingEvent, ...]
    line_id: str
    configuration_fingerprint: str
    processing_started_at: datetime
    processing_finished_at: datetime
    crossing_latency_ms: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or fullmatch(_SOURCE_ID, self.source_id) is None:
            raise InputDataError("Crossing result source ID must be opaque text.")
        if (
            not isinstance(self.tracker_lifecycle_id, str)
            or fullmatch(_OPAQUE_ID, self.tracker_lifecycle_id) is None
        ):
            raise InputDataError("Crossing result lifecycle ID must be opaque text.")
        _non_negative_integer(self.frame_sequence, "Crossing result frame sequence")
        _aware_datetime(self.captured_at, "Crossing result capture time")
        if not isinstance(self.observations, tuple) or not all(
            isinstance(item, TrackCrossingObservation) for item in self.observations
        ):
            raise InputDataError("Crossing observations must be an immutable tuple.")
        if not isinstance(self.events, tuple) or not all(
            isinstance(item, LiveCrossingEvent) for item in self.events
        ):
            raise InputDataError("Crossing events must be an immutable tuple.")
        event_ids = [item.tracker_id for item in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise InputDataError("One tracker may emit at most one crossing event per frame.")
        if not isinstance(self.line_id, str) or fullmatch(_OPAQUE_ID, self.line_id) is None:
            raise InputDataError("Crossing result line ID must be opaque text.")
        if fullmatch(_SHA256, self.configuration_fingerprint) is None:
            raise InputDataError("Crossing result fingerprint must be SHA-256 text.")
        _aware_datetime(self.processing_started_at, "Crossing processing start")
        _aware_datetime(self.processing_finished_at, "Crossing processing finish")
        if self.processing_finished_at < self.processing_started_at:
            raise InputDataError("Crossing completion cannot precede its start.")
        if (
            not isinstance(self.crossing_latency_ms, (int, float))
            or isinstance(self.crossing_latency_ms, bool)
            or not isfinite(self.crossing_latency_ms)
            or float(self.crossing_latency_ms) < 0
        ):
            raise InputDataError("Crossing latency must be a finite non-negative number.")
        object.__setattr__(self, "crossing_latency_ms", float(self.crossing_latency_ms))


@dataclass(frozen=True, slots=True)
class LiveCrossingStats:
    """Bounded diagnostic telemetry; event totals are not animal counts."""

    requests_processed: int
    successful_results: int
    failures: int
    tracks_observed: int
    tracks_initialized: int
    tracks_on_line: int
    events_emitted: int
    negative_to_positive_events: int
    positive_to_negative_events: int
    active_identities_current: int
    active_identities_peak: int
    resets: int
    closes: int
    stale_requests_rejected: int
    preview_failures: int
    total_crossing_latency_ms: float
    average_crossing_latency_ms: float
    maximum_crossing_latency_ms: float
    last_frame_sequence: int | None
    last_error: LiveCrossingErrorCategory
    health_state: LiveCrossingHealthState

    def __post_init__(self) -> None:
        for name in (
            "requests_processed",
            "successful_results",
            "failures",
            "tracks_observed",
            "tracks_initialized",
            "tracks_on_line",
            "events_emitted",
            "negative_to_positive_events",
            "positive_to_negative_events",
            "active_identities_current",
            "active_identities_peak",
            "resets",
            "closes",
            "stale_requests_rejected",
            "preview_failures",
        ):
            _non_negative_integer(getattr(self, name), name)
        for name in (
            "total_crossing_latency_ms",
            "average_crossing_latency_ms",
            "maximum_crossing_latency_ms",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(value)
                or float(value) < 0
            ):
                raise InputDataError(f"{name} must be a finite non-negative number.")
        if self.last_frame_sequence is not None:
            _non_negative_integer(self.last_frame_sequence, "Last crossing frame sequence")
        if not isinstance(self.last_error, LiveCrossingErrorCategory):
            raise InputDataError("Last crossing error category must be explicit.")
        if not isinstance(self.health_state, LiveCrossingHealthState):
            raise InputDataError("Crossing health state must be explicit.")
        if self.requests_processed != self.successful_results + self.failures:
            raise InputDataError("Crossing accounting requires requests = successes + failures.")
        if self.events_emitted != (
            self.negative_to_positive_events + self.positive_to_negative_events
        ):
            raise InputDataError("Crossing event direction totals must equal emitted events.")


@dataclass(frozen=True, slots=True)
class LiveCrossingSnapshot:
    """Current tracking and crossing telemetry without frame or event history."""

    tracking: LiveTrackingSnapshot
    crossing: LiveCrossingStats

    def __post_init__(self) -> None:
        if not isinstance(self.tracking, LiveTrackingSnapshot):
            raise InputDataError("Crossing snapshot requires live tracking telemetry.")
        if not isinstance(self.crossing, LiveCrossingStats):
            raise InputDataError("Crossing snapshot statistics are invalid.")


@dataclass(frozen=True, slots=True)
class LiveCrossingRunSummary:
    """Terminal tracking and crossing state for one live run."""

    tracking_summary: LiveTrackingRunSummary
    crossing_statistics: LiveCrossingStats
    configuration_fingerprint: str
    crossing_closed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.tracking_summary, LiveTrackingRunSummary):
            raise InputDataError("Crossing summary requires a live tracking summary.")
        if not isinstance(self.crossing_statistics, LiveCrossingStats):
            raise InputDataError("Crossing summary statistics are invalid.")
        if fullmatch(_SHA256, self.configuration_fingerprint) is None:
            raise InputDataError("Crossing summary fingerprint must be SHA-256 text.")
        if not isinstance(self.crossing_closed, bool):
            raise InputDataError("Crossing summary close state must be boolean.")


__all__ = [
    "LineSide",
    "LiveCrossingConfiguration",
    "LiveCrossingDirection",
    "LiveCrossingErrorCategory",
    "LiveCrossingEvent",
    "LiveCrossingHealthState",
    "LiveCrossingResult",
    "LiveCrossingRunSummary",
    "LiveCrossingSnapshot",
    "LiveCrossingStats",
    "NormalizedLine",
    "NormalizedPoint",
    "TrackAnchor",
    "TrackCrossingObservation",
]
