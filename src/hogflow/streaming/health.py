"""Thread-safe bounded health and statistics aggregation for stream lifecycles."""

from __future__ import annotations

from threading import RLock
from time import monotonic
from typing import Callable

from hogflow.core import InputDataError
from hogflow.streaming.models import (
    BufferStatistics,
    FrameDimensions,
    StreamErrorCategory,
    StreamHealth,
    StreamHealthState,
    StreamIdentity,
    StreamStatistics,
)


class StreamHealthMonitor:
    """Maintain aggregate counters and one current sanitized health snapshot.

    The monitor stores no exception messages and no history collection, so
    diagnostics remain bounded for effectively unbounded stream lifecycles.
    """

    def __init__(
        self,
        identity: StreamIdentity,
        *,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(identity, StreamIdentity):
            raise InputDataError("Health monitor identity must be StreamIdentity.")
        self._identity = identity
        self._clock = monotonic_clock
        self._lock = RLock()
        self._started_at = float(self._clock())
        self._state = StreamHealthState.CREATED
        self._error_category = StreamErrorCategory.NONE
        self._open_attempts = 0
        self._successful_opens = 0
        self._frames_acquired = 0
        self._temporary_failures = 0
        self._fatal_failures = 0
        self._reconnects = 0
        self._consecutive_failures = 0
        self._last_success: float | None = None
        self._previous_success: float | None = None
        self._interval_sum = 0.0
        self._interval_count = 0
        self._reported_fps: float | None = None
        self._observed_dimensions: FrameDimensions | None = None
        self._last_sequence: int | None = None

    def transition(
        self,
        state: StreamHealthState,
        category: StreamErrorCategory = StreamErrorCategory.NONE,
    ) -> None:
        """Record one current lifecycle state and sanitized category."""

        if not isinstance(state, StreamHealthState) or not isinstance(
            category, StreamErrorCategory
        ):
            raise InputDataError("Stream health transition values are invalid.")
        with self._lock:
            self._state = state
            self._error_category = category

    def record_open_attempt(self) -> None:
        """Increment source-open attempts."""

        with self._lock:
            self._open_attempts += 1
            self._state = StreamHealthState.OPENING

    def record_open_success(self) -> None:
        """Record an acquired source resource."""

        with self._lock:
            self._successful_opens += 1
            self._state = StreamHealthState.RUNNING
            self._error_category = StreamErrorCategory.NONE

    def record_frame(
        self,
        dimensions: FrameDimensions,
        *,
        sequence_number: int | None = None,
        at_monotonic: float | None = None,
    ) -> None:
        """Record one successful frame and update interval-based FPS."""

        if not isinstance(dimensions, FrameDimensions):
            raise InputDataError("Observed frame dimensions must be FrameDimensions.")
        now = float(self._clock()) if at_monotonic is None else float(at_monotonic)
        if now < 0:
            raise InputDataError("Monotonic frame time must be non-negative.")
        with self._lock:
            if self._previous_success is not None:
                interval = now - self._previous_success
                if interval < 0:
                    raise InputDataError("Monotonic frame time must not move backward.")
                self._interval_sum += interval
                self._interval_count += 1
            self._previous_success = now
            self._last_success = now
            self._observed_dimensions = dimensions
            self._frames_acquired += 1
            self._consecutive_failures = 0
            self._state = StreamHealthState.RUNNING
            self._error_category = StreamErrorCategory.NONE
            if sequence_number is not None:
                self._last_sequence = sequence_number

    def record_observed_settings(
        self,
        dimensions: FrameDimensions | None,
        observed_fps: float | None,
    ) -> None:
        """Record source-reported settings without claiming they were honored."""

        if dimensions is not None and not isinstance(dimensions, FrameDimensions):
            raise InputDataError("Observed source dimensions must be FrameDimensions.")
        if observed_fps is not None and observed_fps <= 0:
            raise InputDataError("Observed source FPS must be positive when provided.")
        with self._lock:
            if dimensions is not None:
                self._observed_dimensions = dimensions
            if observed_fps is not None and self._interval_count == 0:
                self._reported_fps = float(observed_fps)

    def record_temporary_failure(
        self,
        category: StreamErrorCategory = StreamErrorCategory.READ,
    ) -> int:
        """Record one temporary failure and return its consecutive count."""

        with self._lock:
            self._temporary_failures += 1
            self._consecutive_failures += 1
            self._state = StreamHealthState.DEGRADED
            self._error_category = category
            return self._consecutive_failures

    def record_fatal_failure(self, category: StreamErrorCategory) -> None:
        """Record one fatal failure without retaining an exception message."""

        with self._lock:
            self._fatal_failures += 1
            self._state = StreamHealthState.FAILED
            self._error_category = category

    def record_reconnect(self) -> None:
        """Record one scheduled live-source reconnection."""

        with self._lock:
            self._reconnects += 1
            self._state = StreamHealthState.RECONNECTING

    def health(self, buffer: BufferStatistics | None = None) -> StreamHealth:
        """Return current health merged with optional buffer depth."""

        with self._lock:
            return StreamHealth(
                identity=self._identity,
                state=self._state,
                consecutive_read_failures=self._consecutive_failures,
                last_success_monotonic_seconds=self._last_success,
                observed_dimensions=self._observed_dimensions,
                observed_fps=self._observed_fps(),
                current_buffer_depth=buffer.current_depth if buffer else 0,
                last_error_category=self._error_category,
            )

    def statistics(self, buffer: BufferStatistics | None = None) -> StreamStatistics:
        """Return aggregate counters merged with an optional buffer snapshot."""

        now = float(self._clock())
        with self._lock:
            return StreamStatistics(
                open_attempts=self._open_attempts,
                successful_opens=self._successful_opens,
                frames_acquired=self._frames_acquired,
                frames_submitted=buffer.frames_submitted if buffer else 0,
                frames_delivered=buffer.frames_delivered if buffer else 0,
                frames_dropped=buffer.frames_dropped if buffer else 0,
                temporary_read_failures=self._temporary_failures,
                fatal_read_failures=self._fatal_failures,
                reconnect_count=self._reconnects,
                current_buffer_depth=buffer.current_depth if buffer else 0,
                maximum_buffer_depth=buffer.maximum_observed_depth if buffer else 0,
                last_frame_sequence_number=self._last_sequence,
                observed_fps=self._observed_fps(),
                average_acquisition_interval_seconds=self._average_interval(),
                runtime_seconds=max(0.0, now - self._started_at),
            )

    def _average_interval(self) -> float | None:
        if not self._interval_count:
            return None
        return self._interval_sum / self._interval_count

    def _observed_fps(self) -> float | None:
        average = self._average_interval()
        return self._reported_fps if average is None or average <= 0 else 1.0 / average


__all__ = ["StreamHealthMonitor"]
