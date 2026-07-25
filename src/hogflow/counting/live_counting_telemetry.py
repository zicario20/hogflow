"""Thread-safe bounded telemetry for lifecycle directional counting."""

from __future__ import annotations

from threading import RLock

from hogflow.core import InputDataError
from hogflow.counting.live_counting_models import (
    CountingDecisionType,
    LiveCountingErrorCategory,
    LiveCountingHealthState,
    LiveCountingResult,
    LiveCountingStats,
)


class LiveCountingTelemetry:
    """Aggregate decisions and errors without retaining event history."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._results = 0
        self._events = 0
        self._positives = 0
        self._duplicates = 0
        self._reverses_before = 0
        self._reverses_after = 0
        self._current_total = 0
        self._current_identities = 0
        self._peak_identities = 0
        self._frames_without_events = 0
        self._resets = 0
        self._closes = 0
        self._stale = 0
        self._lifecycle_mismatches = 0
        self._failures = 0
        self._preview_failures = 0
        self._total_latency = 0.0
        self._maximum_latency = 0.0
        self._last_frame: int | None = None
        self._last_error = LiveCountingErrorCategory.NONE
        self._health = LiveCountingHealthState.CREATED

    def record_started(self) -> None:
        with self._lock:
            self._current_total = 0
            self._current_identities = 0
            self._last_frame = None
            self._health = LiveCountingHealthState.RUNNING
            self._last_error = LiveCountingErrorCategory.NONE

    def record_success(self, result: LiveCountingResult) -> None:
        if not isinstance(result, LiveCountingResult):
            raise InputDataError("Counting telemetry requires LiveCountingResult.")
        positives = sum(
            item.decision_type is CountingDecisionType.COUNTED_POSITIVE for item in result.decisions
        )
        duplicates = sum(
            item.decision_type is CountingDecisionType.IGNORED_DUPLICATE_POSITIVE
            for item in result.decisions
        )
        reverse_decisions = tuple(
            item
            for item in result.decisions
            if item.decision_type is CountingDecisionType.IGNORED_REVERSE
        )
        with self._lock:
            self._results += 1
            self._events += len(result.decisions)
            self._positives += positives
            self._duplicates += duplicates
            self._reverses_before += sum(
                not item.identity_previously_counted for item in reverse_decisions
            )
            self._reverses_after += sum(
                item.identity_previously_counted for item in reverse_decisions
            )
            self._current_total = result.lifecycle_directional_count
            self._current_identities = result.counted_identities_current
            self._peak_identities = max(self._peak_identities, self._current_identities)
            self._frames_without_events += int(not result.decisions)
            self._total_latency += result.counting_latency_ms
            self._maximum_latency = max(
                self._maximum_latency,
                result.counting_latency_ms,
            )
            self._last_frame = result.frame_sequence
            self._last_error = LiveCountingErrorCategory.NONE
            self._health = LiveCountingHealthState.RUNNING

    def record_failure(
        self,
        category: LiveCountingErrorCategory,
        *,
        stale: bool = False,
        lifecycle_mismatch: bool = False,
    ) -> None:
        if (
            not isinstance(category, LiveCountingErrorCategory)
            or not isinstance(stale, bool)
            or not isinstance(lifecycle_mismatch, bool)
        ):
            raise InputDataError("Counting failure telemetry requires explicit values.")
        with self._lock:
            self._failures += 1
            self._stale += int(stale)
            self._lifecycle_mismatches += int(lifecycle_mismatch)
            self._last_error = category
            self._health = LiveCountingHealthState.FAILED

    def record_reset(self) -> None:
        with self._lock:
            self._resets += 1
            self._current_total = 0
            self._current_identities = 0
            self._last_frame = None
            self._last_error = LiveCountingErrorCategory.NONE
            self._health = LiveCountingHealthState.RUNNING

    def record_preview_failure(self) -> None:
        with self._lock:
            self._preview_failures += 1
            self._last_error = LiveCountingErrorCategory.PREVIEW

    def record_closed(self) -> None:
        with self._lock:
            self._closes += 1
            self._health = LiveCountingHealthState.STOPPED

    def snapshot(self) -> LiveCountingStats:
        with self._lock:
            average = self._total_latency / self._results if self._results else 0.0
            reverses = self._reverses_before + self._reverses_after
            return LiveCountingStats(
                crossing_results_processed=self._results,
                crossing_events_processed=self._events,
                positives_counted=self._positives,
                duplicate_positives=self._duplicates,
                reverses=reverses,
                reverses_before_count=self._reverses_before,
                reverses_after_count=self._reverses_after,
                lifecycle_directional_count=self._current_total,
                counted_identities_current=self._current_identities,
                counted_identities_peak=self._peak_identities,
                frames_without_events=self._frames_without_events,
                resets=self._resets,
                closes=self._closes,
                stale_requests_rejected=self._stale,
                lifecycle_mismatches=self._lifecycle_mismatches,
                failures=self._failures,
                preview_failures=self._preview_failures,
                total_counting_latency_ms=self._total_latency,
                average_counting_latency_ms=average,
                maximum_counting_latency_ms=self._maximum_latency,
                last_frame_sequence=self._last_frame,
                last_error=self._last_error,
                health_state=self._health,
            )


__all__ = ["LiveCountingTelemetry"]
