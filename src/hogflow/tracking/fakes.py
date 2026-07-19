"""Deterministic framework-free live trackers for tests and diagnostics."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from time import monotonic, sleep
from typing import Callable

from hogflow.core import ConfigurationError, InputDataError
from hogflow.models import BoundingBox, Detection, Track
from hogflow.tracking.errors import (
    FatalTrackingError,
    StaleTrackingRequestError,
    TemporaryTrackingError,
    TrackerLifecycleError,
)
from hogflow.tracking.models import (
    TrackedObject,
    TrackerMetadata,
    TrackingRequest,
    TrackingResult,
    TrackState,
)

_SYNTHETIC_CONFIGURATION = hashlib.sha256(b"hogflow-synthetic-tracker-v1").hexdigest()


class EmptyTracker:
    """Return no tracks while exercising the complete live tracker lifecycle."""

    def __init__(
        self,
        *,
        tracker_id: str = "empty-tracker",
        monotonic_clock: Callable[[], float] = monotonic,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._metadata = TrackerMetadata(
            tracker_id=tracker_id,
            framework="synthetic",
            framework_version="1",
            configuration_fingerprint=_SYNTHETIC_CONFIGURATION,
        )
        self._monotonic = monotonic_clock
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._started = False
        self._stream_id: str | None = None
        self._last_sequence: int | None = None
        self.reset_count = 0
        self.close_count = 0
        self.updated_sequences: list[int] = []

    @property
    def metadata(self) -> TrackerMetadata:
        return self._metadata

    @property
    def is_started(self) -> bool:
        return self._started

    def start(self, stream_id: str) -> None:
        if not isinstance(stream_id, str) or not stream_id:
            raise InputDataError("Synthetic tracker stream ID must be non-empty text.")
        if self._started:
            if stream_id != self._stream_id:
                raise TrackerLifecycleError("One tracker lifecycle cannot mix source streams.")
            return
        self._stream_id = stream_id
        self._started = True
        self._last_sequence = None
        self._reset_state()

    def update(self, request: TrackingRequest) -> TrackingResult:
        self._validate_request(request)
        started_monotonic = float(self._monotonic())
        started_at = self._wall_clock()
        tracked_objects = self._objects_for(request)
        completed_monotonic = float(self._monotonic())
        completed_at = self._wall_clock()
        self._last_sequence = request.frame_sequence
        self.updated_sequences.append(request.frame_sequence)
        return TrackingResult(
            source_id=request.source_id,
            frame_sequence=request.frame_sequence,
            captured_at=request.captured_at,
            frame_width=request.frame_width,
            frame_height=request.frame_height,
            tracked_objects=tracked_objects,
            tracker_id=self.metadata.tracker_id,
            tracker_version=self.metadata.framework_version,
            configuration_fingerprint=self.metadata.configuration_fingerprint,
            processing_started_at=started_at,
            processing_finished_at=completed_at,
            tracking_latency_ms=max(0.0, completed_monotonic - started_monotonic) * 1000,
        )

    def reset(self) -> None:
        if not self._started:
            raise TrackerLifecycleError("Tracker must be started before reset.")
        self._last_sequence = None
        self.reset_count += 1
        self._reset_state()

    def close(self) -> None:
        if not self._started:
            return
        self._started = False
        self._stream_id = None
        self._last_sequence = None
        self.close_count += 1
        self._reset_state()

    def _validate_request(self, request: TrackingRequest) -> None:
        if not self._started or self._stream_id is None:
            raise TrackerLifecycleError("Tracker must be started before update.")
        if not isinstance(request, TrackingRequest):
            raise InputDataError("Live tracker input must be a TrackingRequest.")
        if request.source_id != self._stream_id:
            raise TrackerLifecycleError("One tracker lifecycle cannot mix source streams.")
        if self._last_sequence is not None and request.frame_sequence <= self._last_sequence:
            raise StaleTrackingRequestError("Tracking requests must have increasing frame IDs.")

    def _objects_for(self, _request: TrackingRequest) -> tuple[TrackedObject, ...]:
        return ()

    def _reset_state(self) -> None:
        return None


class ScriptedTracker(EmptyTracker):
    """Return predefined immutable visible tracks for selected frame IDs."""

    def __init__(
        self,
        objects_by_sequence: Mapping[int, tuple[TrackedObject, ...]],
        **settings: object,
    ) -> None:
        if not isinstance(objects_by_sequence, Mapping):
            raise InputDataError("Scripted tracks must be a sequence mapping.")
        script: dict[int, tuple[TrackedObject, ...]] = {}
        for sequence, objects in objects_by_sequence.items():
            if (
                not isinstance(sequence, int)
                or isinstance(sequence, bool)
                or sequence < 0
                or not isinstance(objects, tuple)
                or not all(isinstance(item, TrackedObject) for item in objects)
            ):
                raise InputDataError("Scripted tracker entries must map frame IDs to tuples.")
            script[sequence] = objects
        super().__init__(tracker_id="scripted-tracker", **settings)
        self._script = script

    def _objects_for(self, request: TrackingRequest) -> tuple[TrackedObject, ...]:
        return self._script.get(request.frame_sequence, ())


@dataclass(slots=True)
class _IoUTrackState:
    track_id: int
    detection: Detection
    first_sequence: int
    last_sequence: int
    hits: int


class DeterministicIoUTracker(EmptyTracker):
    """Small deterministic IoU tracker for tests, never production tracking.

    It performs confidence-independent greedy same-class IoU association with
    stable track-ID tie-breaking. It is intentionally simple and makes no
    claim about real occlusion, motion, or pig-tracking quality.
    """

    def __init__(
        self,
        *,
        iou_threshold: float = 0.3,
        lost_track_buffer: int = 2,
        **settings: object,
    ) -> None:
        if (
            not isinstance(iou_threshold, (int, float))
            or isinstance(iou_threshold, bool)
            or not isfinite(iou_threshold)
            or not 0.0 <= float(iou_threshold) <= 1.0
        ):
            raise ConfigurationError("Deterministic IoU threshold must be from 0 through 1.")
        if (
            not isinstance(lost_track_buffer, int)
            or isinstance(lost_track_buffer, bool)
            or lost_track_buffer < 0
        ):
            raise ConfigurationError("Deterministic lost-track buffer must be non-negative.")
        fingerprint = hashlib.sha256(
            f"iou={float(iou_threshold):.12g};lost={lost_track_buffer}".encode()
        ).hexdigest()
        super().__init__(tracker_id="deterministic-iou-tracker", **settings)
        self._metadata = TrackerMetadata(
            tracker_id="deterministic-iou-tracker",
            framework="synthetic",
            framework_version="1",
            configuration_fingerprint=fingerprint,
        )
        self._iou_threshold = float(iou_threshold)
        self._lost_track_buffer = lost_track_buffer
        self._tracks: dict[int, _IoUTrackState] = {}
        self._next_track_id = 0

    def _reset_state(self) -> None:
        self._tracks = {}
        self._next_track_id = 0

    def _objects_for(self, request: TrackingRequest) -> tuple[TrackedObject, ...]:
        self._tracks = {
            track_id: state
            for track_id, state in self._tracks.items()
            if request.frame_sequence - state.last_sequence - 1 <= self._lost_track_buffer
        }
        unmatched_track_ids = set(self._tracks)
        visible: list[TrackedObject] = []
        for detection_index, detection in enumerate(request.detections):
            candidates = [
                (self._iou_threshold_value(detection, self._tracks[track_id].detection), track_id)
                for track_id in unmatched_track_ids
                if self._tracks[track_id].detection.class_id == detection.class_id
            ]
            candidates = [item for item in candidates if item[0] >= self._iou_threshold]
            if candidates:
                _, track_id = min(candidates, key=lambda item: (-item[0], item[1]))
                state = self._tracks[track_id]
                state.detection = detection
                state.last_sequence = request.frame_sequence
                state.hits += 1
                unmatched_track_ids.remove(track_id)
            else:
                track_id = self._next_track_id
                self._next_track_id += 1
                state = _IoUTrackState(
                    track_id=track_id,
                    detection=detection,
                    first_sequence=request.frame_sequence,
                    last_sequence=request.frame_sequence,
                    hits=1,
                )
                self._tracks[track_id] = state
            visible.append(
                TrackedObject(
                    track=Track(track_id, detection),
                    source_detection_index=detection_index,
                    state=TrackState.VISIBLE,
                    age_frames=request.frame_sequence - state.first_sequence + 1,
                    hits=state.hits,
                    missed_frames=0,
                )
            )
        return tuple(sorted(visible, key=lambda item: item.track.tracker_id))

    @staticmethod
    def _iou_threshold_value(left: Detection, right: Detection) -> float:
        a = left.bounding_box
        b = right.bounding_box
        x_min = max(a.x_min, b.x_min)
        y_min = max(a.y_min, b.y_min)
        x_max = min(a.x_max, b.x_max)
        y_max = min(a.y_max, b.y_max)
        intersection = max(0.0, x_max - x_min) * max(0.0, y_max - y_min)
        area_a = (a.x_max - a.x_min) * (a.y_max - a.y_min)
        area_b = (b.x_max - b.x_min) * (b.y_max - b.y_min)
        union = area_a + area_b - intersection
        return intersection / union if union > 0 else 0.0


class SlowTracker(DeterministicIoUTracker):
    """Add an injected deterministic delay before each synthetic update."""

    def __init__(
        self,
        *,
        delay_seconds: float = 0.05,
        sleeper: Callable[[float], object] = sleep,
        **settings: object,
    ) -> None:
        if (
            not isinstance(delay_seconds, (int, float))
            or isinstance(delay_seconds, bool)
            or not isfinite(delay_seconds)
            or delay_seconds < 0
        ):
            raise ConfigurationError("Slow-tracker delay must be non-negative.")
        super().__init__(**settings)
        self._delay = float(delay_seconds)
        self._sleeper = sleeper

    def _objects_for(self, request: TrackingRequest) -> tuple[TrackedObject, ...]:
        self._sleeper(self._delay)
        return super()._objects_for(request)


class FailingTracker(DeterministicIoUTracker):
    """Raise configured recoverable or fatal failures by frame sequence."""

    def __init__(
        self,
        *,
        temporary_sequences: tuple[int, ...] = (),
        fatal_sequences: tuple[int, ...] = (),
        **settings: object,
    ) -> None:
        for values in (temporary_sequences, fatal_sequences):
            if not isinstance(values, tuple) or not all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in values
            ):
                raise InputDataError("Tracking failure sequences must be non-negative integers.")
        if set(temporary_sequences) & set(fatal_sequences):
            raise InputDataError("A frame cannot be both temporarily and fatally failing.")
        super().__init__(**settings)
        self._temporary = frozenset(temporary_sequences)
        self._fatal = frozenset(fatal_sequences)

    def update(self, request: TrackingRequest) -> TrackingResult:
        self._validate_request(request)
        if request.frame_sequence in self._temporary:
            self._last_sequence = request.frame_sequence
            self.updated_sequences.append(request.frame_sequence)
            raise TemporaryTrackingError("Synthetic temporary tracker failure.")
        if request.frame_sequence in self._fatal:
            raise FatalTrackingError("Synthetic fatal tracker failure.")
        return super().update(request)


def synthetic_tracked_object(
    track_id: int,
    bounding_box: BoundingBox,
    *,
    confidence: float = 0.9,
    class_id: int = 0,
    class_name: str = "pig",
    source_detection_index: int | None = None,
) -> TrackedObject:
    """Build one immutable visible object for deterministic tests."""

    return TrackedObject(
        Track(track_id, Detection(bounding_box, confidence, class_id, class_name)),
        source_detection_index=source_detection_index,
    )


__all__ = [
    "DeterministicIoUTracker",
    "EmptyTracker",
    "FailingTracker",
    "ScriptedTracker",
    "SlowTracker",
    "synthetic_tracked_object",
]
