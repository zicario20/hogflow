"""Thread-safe bounded aggregate telemetry for live tracking."""

from __future__ import annotations

from threading import RLock

from hogflow.core import InputDataError
from hogflow.tracking.models import (
    LiveTrackingStats,
    TrackingErrorCategory,
    TrackingHealthState,
    TrackingRequest,
    TrackingResult,
)


class LiveTrackingTelemetry:
    """Aggregate counters and latency without retaining frames or track history."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._requests = 0
        self._successes = 0
        self._failures = 0
        self._lifecycle_failures = 0
        self._zero_detection_updates = 0
        self._tracks_emitted = 0
        self._active_current = 0
        self._active_peak = 0
        self._frames_with_tracks = 0
        self._frames_without_tracks = 0
        self._resets = 0
        self._restarts = 0
        self._closes = 0
        self._stale = 0
        self._malformed = 0
        self._preview_failures = 0
        self._total_latency = 0.0
        self._last_latency = 0.0
        self._maximum_latency = 0.0
        self._last_frame_id: int | None = None
        self._last_error = TrackingErrorCategory.NONE
        self._health = TrackingHealthState.CREATED

    def record_starting(self) -> None:
        with self._lock:
            self._health = TrackingHealthState.STARTING

    def record_started(self) -> None:
        with self._lock:
            self._health = TrackingHealthState.RUNNING
            self._last_error = TrackingErrorCategory.NONE

    def record_request(self, request: TrackingRequest) -> None:
        if not isinstance(request, TrackingRequest):
            raise InputDataError("Tracking telemetry requires TrackingRequest.")
        with self._lock:
            self._requests += 1
            if not request.detections:
                self._zero_detection_updates += 1

    def record_success(self, result: TrackingResult) -> None:
        if not isinstance(result, TrackingResult):
            raise InputDataError("Tracking telemetry requires TrackingResult.")
        with self._lock:
            visible = len(result.tracked_objects)
            self._successes += 1
            self._tracks_emitted += visible
            self._active_current = visible
            self._active_peak = max(self._active_peak, visible)
            if visible:
                self._frames_with_tracks += 1
            else:
                self._frames_without_tracks += 1
            self._total_latency += result.tracking_latency_ms
            self._last_latency = result.tracking_latency_ms
            self._maximum_latency = max(self._maximum_latency, result.tracking_latency_ms)
            self._last_frame_id = result.frame_sequence
            self._last_error = TrackingErrorCategory.NONE
            self._health = TrackingHealthState.RUNNING

    def record_failure(
        self,
        category: TrackingErrorCategory,
        *,
        fatal: bool,
        stale: bool = False,
        malformed: bool = False,
    ) -> None:
        if not isinstance(category, TrackingErrorCategory) or not isinstance(fatal, bool):
            raise InputDataError("Tracking failure telemetry requires explicit values.")
        with self._lock:
            self._failures += 1
            self._active_current = 0
            self._last_error = category
            self._health = TrackingHealthState.FAILED if fatal else TrackingHealthState.DEGRADED
            if stale:
                self._stale += 1
            if malformed:
                self._malformed += 1

    def record_reset(self, *, reconnect: bool = False) -> None:
        with self._lock:
            self._resets += 1
            self._restarts += int(reconnect)
            self._active_current = 0
            self._health = TrackingHealthState.RUNNING
            self._last_error = TrackingErrorCategory.NONE

    def record_lifecycle_failure(
        self,
        category: TrackingErrorCategory,
        *,
        fatal: bool,
    ) -> None:
        """Record startup, reset, or close failure outside update accounting."""

        if not isinstance(category, TrackingErrorCategory) or not isinstance(fatal, bool):
            raise InputDataError("Tracking lifecycle telemetry requires explicit values.")
        with self._lock:
            self._lifecycle_failures += 1
            self._last_error = category
            self._health = TrackingHealthState.FAILED if fatal else TrackingHealthState.DEGRADED

    def record_preview_failure(self) -> None:
        with self._lock:
            self._preview_failures += 1

    def record_stopping(self) -> None:
        with self._lock:
            self._health = TrackingHealthState.STOPPING

    def record_closed(self) -> None:
        with self._lock:
            self._closes += 1
            self._active_current = 0
            self._health = TrackingHealthState.STOPPED

    def snapshot(self) -> LiveTrackingStats:
        with self._lock:
            average = self._total_latency / self._successes if self._successes else 0.0
            return LiveTrackingStats(
                tracking_requests=self._requests,
                tracking_successes=self._successes,
                tracking_failures=self._failures,
                lifecycle_failures=self._lifecycle_failures,
                zero_detection_updates=self._zero_detection_updates,
                tracks_emitted=self._tracks_emitted,
                active_tracks_current=self._active_current,
                active_tracks_peak=self._active_peak,
                frames_with_tracks=self._frames_with_tracks,
                frames_without_tracks=self._frames_without_tracks,
                tracker_resets=self._resets,
                tracker_restarts=self._restarts,
                tracker_closes=self._closes,
                stale_requests_rejected=self._stale,
                malformed_detections_rejected=self._malformed,
                preview_failures=self._preview_failures,
                total_tracking_latency_ms=self._total_latency,
                last_tracking_latency_ms=self._last_latency,
                average_tracking_latency_ms=average,
                maximum_tracking_latency_ms=self._maximum_latency,
                last_tracking_frame_id=self._last_frame_id,
                last_tracking_error=self._last_error,
                current_health_state=self._health,
            )


__all__ = ["LiveTrackingTelemetry"]
