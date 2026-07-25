"""Thread-safe bounded aggregate telemetry for live crossing events."""

from __future__ import annotations

from threading import RLock

from hogflow.core import InputDataError
from hogflow.counting.live_models import (
    LineSide,
    LiveCrossingDirection,
    LiveCrossingErrorCategory,
    LiveCrossingHealthState,
    LiveCrossingResult,
    LiveCrossingStats,
)


class LiveCrossingTelemetry:
    """Aggregate crossing diagnostics without retaining events or frames."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._requests = 0
        self._successes = 0
        self._failures = 0
        self._tracks_observed = 0
        self._tracks_initialized = 0
        self._tracks_on_line = 0
        self._events = 0
        self._negative_to_positive = 0
        self._positive_to_negative = 0
        self._active_current = 0
        self._active_peak = 0
        self._resets = 0
        self._closes = 0
        self._stale = 0
        self._preview_failures = 0
        self._total_latency = 0.0
        self._maximum_latency = 0.0
        self._last_frame: int | None = None
        self._last_error = LiveCrossingErrorCategory.NONE
        self._health = LiveCrossingHealthState.CREATED

    def record_started(self) -> None:
        with self._lock:
            self._health = LiveCrossingHealthState.RUNNING
            self._last_error = LiveCrossingErrorCategory.NONE

    def record_request(self) -> None:
        with self._lock:
            self._requests += 1

    def record_success(self, result: LiveCrossingResult, *, initialized: int, active: int) -> None:
        if not isinstance(result, LiveCrossingResult):
            raise InputDataError("Crossing telemetry requires LiveCrossingResult.")
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in (initialized, active)
        ):
            raise InputDataError("Crossing telemetry values must be non-negative integers.")
        with self._lock:
            self._successes += 1
            self._tracks_observed += len(result.observations)
            self._tracks_initialized += initialized
            self._tracks_on_line += sum(
                observation.side is LineSide.ON_LINE for observation in result.observations
            )
            self._events += len(result.events)
            self._negative_to_positive += sum(
                event.direction is LiveCrossingDirection.NEGATIVE_TO_POSITIVE
                for event in result.events
            )
            self._positive_to_negative += sum(
                event.direction is LiveCrossingDirection.POSITIVE_TO_NEGATIVE
                for event in result.events
            )
            self._active_current = active
            self._active_peak = max(self._active_peak, active)
            self._total_latency += result.crossing_latency_ms
            self._maximum_latency = max(self._maximum_latency, result.crossing_latency_ms)
            self._last_frame = result.frame_sequence
            self._last_error = LiveCrossingErrorCategory.NONE
            self._health = LiveCrossingHealthState.RUNNING

    def record_failure(
        self,
        category: LiveCrossingErrorCategory,
        *,
        stale: bool = False,
    ) -> None:
        if not isinstance(category, LiveCrossingErrorCategory) or not isinstance(stale, bool):
            raise InputDataError("Crossing failure telemetry requires explicit values.")
        with self._lock:
            self._failures += 1
            self._last_error = category
            self._health = LiveCrossingHealthState.FAILED
            self._stale += int(stale)

    def record_reset(self) -> None:
        with self._lock:
            self._resets += 1
            self._active_current = 0
            self._last_error = LiveCrossingErrorCategory.NONE
            self._health = LiveCrossingHealthState.RUNNING

    def record_preview_failure(self) -> None:
        with self._lock:
            self._preview_failures += 1
            self._last_error = LiveCrossingErrorCategory.PREVIEW

    def record_closed(self) -> None:
        with self._lock:
            self._closes += 1
            self._active_current = 0
            self._health = LiveCrossingHealthState.STOPPED

    def snapshot(self) -> LiveCrossingStats:
        with self._lock:
            average = self._total_latency / self._successes if self._successes else 0.0
            return LiveCrossingStats(
                requests_processed=self._requests,
                successful_results=self._successes,
                failures=self._failures,
                tracks_observed=self._tracks_observed,
                tracks_initialized=self._tracks_initialized,
                tracks_on_line=self._tracks_on_line,
                events_emitted=self._events,
                negative_to_positive_events=self._negative_to_positive,
                positive_to_negative_events=self._positive_to_negative,
                active_identities_current=self._active_current,
                active_identities_peak=self._active_peak,
                resets=self._resets,
                closes=self._closes,
                stale_requests_rejected=self._stale,
                preview_failures=self._preview_failures,
                total_crossing_latency_ms=self._total_latency,
                average_crossing_latency_ms=average,
                maximum_crossing_latency_ms=self._maximum_latency,
                last_frame_sequence=self._last_frame,
                last_error=self._last_error,
                health_state=self._health,
            )


__all__ = ["LiveCrossingTelemetry"]
