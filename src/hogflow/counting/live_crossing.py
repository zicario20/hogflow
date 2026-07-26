"""Lifecycle-aware finite virtual-line crossing event detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from re import fullmatch
from time import monotonic
from typing import Callable

from hogflow.core import InputDataError
from hogflow.counting.live_errors import CrossingLifecycleError, StaleCrossingRequestError
from hogflow.counting.live_models import (
    LineSide,
    LiveCrossingConfiguration,
    LiveCrossingDirection,
    LiveCrossingErrorCategory,
    LiveCrossingEvent,
    LiveCrossingResult,
    LiveCrossingStats,
    NormalizedPoint,
    TrackAnchor,
    TrackCrossingObservation,
)
from hogflow.counting.live_telemetry import LiveCrossingTelemetry
from hogflow.models import BoundingBox
from hogflow.tracking.models import TrackingResult

_SOURCE_ID = r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}"
_LIFECYCLE_ID = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"


@dataclass(frozen=True, slots=True)
class _TrackSideState:
    last_stable_side: LineSide | None
    last_stable_point: NormalizedPoint | None
    last_stable_frame_sequence: int | None
    last_seen_update: int


def representative_point(
    bounding_box: BoundingBox,
    frame_width: int,
    frame_height: int,
    anchor: TrackAnchor,
) -> NormalizedPoint:
    """Return a deterministic normalized point for one tracked box."""

    if not isinstance(bounding_box, BoundingBox):
        raise InputDataError("Crossing anchor requires a canonical BoundingBox.")
    if (
        not isinstance(frame_width, int)
        or isinstance(frame_width, bool)
        or frame_width <= 0
        or not isinstance(frame_height, int)
        or isinstance(frame_height, bool)
        or frame_height <= 0
    ):
        raise InputDataError("Crossing anchor requires positive frame dimensions.")
    if not isinstance(anchor, TrackAnchor):
        raise InputDataError("Crossing anchor policy must be explicit.")
    x = (bounding_box.x_min + bounding_box.x_max) / 2.0
    y = (
        bounding_box.y_max
        if anchor is TrackAnchor.BOTTOM_CENTER
        else (bounding_box.y_min + bounding_box.y_max) / 2.0
    )
    return NormalizedPoint(x=x / frame_width, y=y / frame_height)


class VirtualLineCrossingDetector:
    """Emit directional finite-segment events without accumulating a count.

    One instance is bound to one source. Temporary tracker IDs are qualified
    by an explicit lifecycle generation that changes on every reset. State is
    retired after a configured number of successful updates in which an ID is
    absent.
    """

    def __init__(
        self,
        configuration: LiveCrossingConfiguration,
        *,
        monotonic_clock: Callable[[], float] = monotonic,
        wall_clock: Callable[[], datetime] | None = None,
        lifecycle_id_factory: Callable[[int], str] | None = None,
    ) -> None:
        if not isinstance(configuration, LiveCrossingConfiguration):
            raise InputDataError("Crossing detector requires LiveCrossingConfiguration.")
        self._configuration = configuration
        self._monotonic = monotonic_clock
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        if lifecycle_id_factory is not None and not callable(lifecycle_id_factory):
            raise InputDataError("Crossing lifecycle ID factory must be callable.")
        self._lifecycle_id_factory = lifecycle_id_factory
        self._telemetry = LiveCrossingTelemetry()
        self._source_id: str | None = None
        self._lifecycle_generation = 0
        self._lifecycle_id: str | None = None
        self._last_sequence: int | None = None
        self._update_index = 0
        self._states: dict[int, _TrackSideState] = {}

    @property
    def configuration(self) -> LiveCrossingConfiguration:
        return self._configuration

    @property
    def is_started(self) -> bool:
        return self._source_id is not None

    @property
    def lifecycle_id(self) -> str:
        if not self.is_started:
            raise CrossingLifecycleError(
                "Crossing lifecycle identity is available only after startup."
            )
        if self._lifecycle_id is None:
            raise CrossingLifecycleError(
                "Crossing lifecycle identity is unavailable before startup."
            )
        return self._lifecycle_id

    def start(self, source_id: str) -> None:
        """Bind the detector to one source and start a fresh lifecycle."""

        if not isinstance(source_id, str) or fullmatch(_SOURCE_ID, source_id) is None:
            raise InputDataError("Crossing source ID must be opaque text.")
        if self.is_started:
            if source_id != self._source_id:
                raise CrossingLifecycleError("One crossing detector cannot mix source streams.")
            return
        self._source_id = source_id
        self._begin_new_lifecycle()
        self._telemetry.record_started()

    def update(self, tracking: TrackingResult) -> LiveCrossingResult:
        """Process current visible tracks and emit observable crossing events."""

        self._telemetry.record_request()
        self._validate_update(tracking)
        line = self._configuration.line
        if line is None:
            self._telemetry.record_failure(LiveCrossingErrorCategory.CONFIGURATION)
            raise CrossingLifecycleError("Crossing update requires an enabled configured line.")

        started_monotonic = float(self._monotonic())
        started_at = self._wall_clock()
        self._update_index += 1
        initialized = 0
        observations: list[TrackCrossingObservation] = []
        events: list[LiveCrossingEvent] = []
        visible_ids: set[int] = set()

        for tracked_object in sorted(
            tracking.tracked_objects,
            key=lambda item: item.track.tracker_id,
        ):
            track = tracked_object.track
            visible_ids.add(track.tracker_id)
            point = representative_point(
                track.detection.bounding_box,
                tracking.frame_width,
                tracking.frame_height,
                self._configuration.anchor,
            )
            side = line.classify(point, self._configuration.epsilon)
            observations.append(TrackCrossingObservation(track.tracker_id, point, side))
            previous = self._states.get(track.tracker_id)
            if side is LineSide.ON_LINE:
                self._states[track.tracker_id] = _TrackSideState(
                    last_stable_side=None if previous is None else previous.last_stable_side,
                    last_stable_point=None if previous is None else previous.last_stable_point,
                    last_stable_frame_sequence=(
                        None if previous is None else previous.last_stable_frame_sequence
                    ),
                    last_seen_update=self._update_index,
                )
                continue

            if previous is None or previous.last_stable_side is None:
                initialized += 1
                self._states[track.tracker_id] = _TrackSideState(
                    side,
                    point,
                    tracking.frame_sequence,
                    self._update_index,
                )
                continue

            if previous.last_stable_side is not side:
                event = self._event_for_transition(
                    tracking, track.tracker_id, previous, point, side
                )
                if event is not None:
                    events.append(event)
            self._states[track.tracker_id] = _TrackSideState(
                side,
                point,
                tracking.frame_sequence,
                self._update_index,
            )

        self._remove_expired_states(visible_ids)
        completed_monotonic = float(self._monotonic())
        completed_at = self._wall_clock()
        result = LiveCrossingResult(
            source_id=tracking.source_id,
            tracker_lifecycle_id=self.lifecycle_id,
            frame_sequence=tracking.frame_sequence,
            captured_at=tracking.captured_at,
            observations=tuple(observations),
            events=tuple(events),
            line_id=f"line-{self._configuration.fingerprint[:16]}",
            configuration_fingerprint=self._configuration.fingerprint,
            processing_started_at=started_at,
            processing_finished_at=completed_at,
            crossing_latency_ms=max(0.0, completed_monotonic - started_monotonic) * 1000,
        )
        self._last_sequence = tracking.frame_sequence
        self._telemetry.record_success(result, initialized=initialized, active=len(self._states))
        return result

    def reset(self) -> None:
        """Discard every remembered side and start a new ID lifecycle."""

        if not self.is_started:
            self._telemetry.record_failure(LiveCrossingErrorCategory.LIFECYCLE)
            raise CrossingLifecycleError("Crossing detector must be started before reset.")
        self._begin_new_lifecycle()
        self._telemetry.record_reset()

    def close(self) -> None:
        """Clear temporary state; repeated calls are safe."""

        if not self.is_started:
            return
        self._states.clear()
        self._source_id = None
        self._lifecycle_id = None
        self._last_sequence = None
        self._update_index = 0
        self._telemetry.record_closed()

    def statistics(self) -> LiveCrossingStats:
        return self._telemetry.snapshot()

    def record_preview_failure(self) -> None:
        """Record one isolated local-preview failure."""

        self._telemetry.record_preview_failure()

    def _validate_update(self, tracking: TrackingResult) -> None:
        if not self.is_started or self._source_id is None:
            self._telemetry.record_failure(LiveCrossingErrorCategory.LIFECYCLE)
            raise CrossingLifecycleError("Crossing detector must be started before update.")
        if not isinstance(tracking, TrackingResult):
            self._telemetry.record_failure(LiveCrossingErrorCategory.INPUT)
            raise InputDataError("Crossing input must be a TrackingResult.")
        if tracking.source_id != self._source_id:
            self._telemetry.record_failure(LiveCrossingErrorCategory.LIFECYCLE)
            raise CrossingLifecycleError("One crossing detector cannot mix source streams.")
        if self._last_sequence is not None and tracking.frame_sequence <= self._last_sequence:
            self._telemetry.record_failure(
                LiveCrossingErrorCategory.STALE,
                stale=True,
            )
            raise StaleCrossingRequestError(
                "Crossing tracking results must have increasing frame sequences."
            )

    def _event_for_transition(
        self,
        tracking: TrackingResult,
        tracker_id: int,
        previous: _TrackSideState,
        current_point: NormalizedPoint,
        current_side: LineSide,
    ) -> LiveCrossingEvent | None:
        previous_point = previous.last_stable_point
        previous_frame = previous.last_stable_frame_sequence
        previous_side = previous.last_stable_side
        line = self._configuration.line
        if (
            previous_point is None
            or previous_frame is None
            or previous_side is None
            or line is None
            or not line.intersects_movement_segment(previous_point, current_point)
        ):
            return None
        direction = (
            LiveCrossingDirection.NEGATIVE_TO_POSITIVE
            if previous_side is LineSide.NEGATIVE
            else LiveCrossingDirection.POSITIVE_TO_NEGATIVE
        )
        return LiveCrossingEvent(
            source_id=tracking.source_id,
            tracker_lifecycle_id=self.lifecycle_id,
            tracker_id=tracker_id,
            frame_sequence=tracking.frame_sequence,
            previous_frame_sequence=previous_frame,
            captured_at=tracking.captured_at,
            direction=direction,
            previous_side=previous_side,
            current_side=current_side,
            previous_point=previous_point,
            representative_point=current_point,
            line_id=f"line-{self._configuration.fingerprint[:16]}",
            configuration_fingerprint=self._configuration.fingerprint,
        )

    def _remove_expired_states(self, visible_ids: set[int]) -> None:
        retention = self._configuration.absent_track_retention_updates
        expired = [
            tracker_id
            for tracker_id, state in self._states.items()
            if tracker_id not in visible_ids
            and self._update_index - state.last_seen_update > retention
        ]
        for tracker_id in expired:
            del self._states[tracker_id]

    def _begin_new_lifecycle(self) -> None:
        self._lifecycle_generation += 1
        lifecycle_id = (
            f"crossing-lifecycle-{self._lifecycle_generation}"
            if self._lifecycle_id_factory is None
            else self._lifecycle_id_factory(self._lifecycle_generation)
        )
        if not isinstance(lifecycle_id, str) or fullmatch(_LIFECYCLE_ID, lifecycle_id) is None:
            raise InputDataError("Crossing lifecycle factory returned invalid opaque text.")
        self._lifecycle_id = lifecycle_id
        self._last_sequence = None
        self._update_index = 0
        self._states.clear()


__all__ = ["VirtualLineCrossingDetector", "representative_point"]
