"""Deterministic framework-free camera source for tests and local diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from threading import RLock
from time import monotonic
from typing import Callable

from hogflow.core import InputDataError
from hogflow.streaming.configuration import StreamConfiguration
from hogflow.streaming.errors import StreamFatalReadError, StreamOpenError
from hogflow.streaming.health import StreamHealthMonitor
from hogflow.streaming.models import (
    FrameDimensions,
    FramePayload,
    SourceFrame,
    StreamErrorCategory,
    StreamHealth,
    StreamHealthState,
    StreamIdentity,
    StreamReadResult,
    StreamReadStatus,
    StreamStatistics,
)


class SyntheticEventType(str, Enum):
    """Scripted synthetic source outcomes."""

    FRAME = "frame"
    TEMPORARY_FAILURE = "temporary_failure"
    INTERRUPTION = "interruption"
    FATAL_FAILURE = "fatal_failure"
    END_OF_STREAM = "end_of_stream"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class SyntheticEvent:
    """One deterministic source event with an optional payload marker."""

    event_type: SyntheticEventType
    marker: int = 0
    retry_after_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, SyntheticEventType):
            raise InputDataError("Synthetic event type is invalid.")
        if (
            not isinstance(self.marker, int)
            or isinstance(self.marker, bool)
            or not 0 <= self.marker <= 255
        ):
            raise InputDataError("Synthetic frame marker must be an integer from 0 through 255.")
        if (
            not isinstance(self.retry_after_seconds, (int, float))
            or isinstance(self.retry_after_seconds, bool)
            or self.retry_after_seconds < 0
        ):
            raise InputDataError("Synthetic retry delay must be non-negative.")


def synthetic_frame_events(frame_count: int) -> tuple[SyntheticEvent, ...]:
    """Create fixed deterministic frame events followed by normal EOF."""

    if not isinstance(frame_count, int) or isinstance(frame_count, bool) or frame_count < 0:
        raise InputDataError("Synthetic frame count must be non-negative.")
    return tuple(
        [
            SyntheticEvent(SyntheticEventType.FRAME, marker=index % 256)
            for index in range(frame_count)
        ]
        + [SyntheticEvent(SyntheticEventType.END_OF_STREAM)]
    )


class SyntheticCameraSource:
    """Script frames, temporary failures, disconnects, fatal errors, and EOF.

    Reopening after an interruption continues at the next scripted event,
    making reconnect tests deterministic without hardware, network access, or
    actual waiting.
    """

    def __init__(
        self,
        *,
        stream_id: str = "synthetic",
        frame_count: int = 0,
        events: tuple[SyntheticEvent, ...] | None = None,
        dimensions: FrameDimensions = FrameDimensions(8, 6, 3),
        frame_interval_seconds: float = 0.1,
        is_live: bool = False,
        open_failures: int = 0,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        self._configuration = StreamConfiguration.synthetic(stream_id)
        if events is None:
            events = synthetic_frame_events(frame_count)
        if not isinstance(events, tuple) or not all(
            isinstance(event, SyntheticEvent) for event in events
        ):
            raise InputDataError("Synthetic events must be an immutable SyntheticEvent tuple.")
        if not isinstance(dimensions, FrameDimensions):
            raise InputDataError("Synthetic dimensions must be FrameDimensions.")
        if (
            not isinstance(frame_interval_seconds, (int, float))
            or isinstance(frame_interval_seconds, bool)
            or frame_interval_seconds < 0
        ):
            raise InputDataError("Synthetic frame interval must be non-negative.")
        if not isinstance(is_live, bool):
            raise InputDataError("Synthetic live state must be boolean.")
        if (
            not isinstance(open_failures, int)
            or isinstance(open_failures, bool)
            or open_failures < 0
        ):
            raise InputDataError("Synthetic open failure count must be non-negative.")
        self._events = events
        self._dimensions = dimensions
        self._interval = float(frame_interval_seconds)
        self._is_live = is_live
        self._remaining_open_failures = open_failures
        self._clock = monotonic_clock
        self._monitor = StreamHealthMonitor(
            self._configuration.identity,
            monotonic_clock=monotonic_clock,
        )
        self._cursor = 0
        self._frame_index = 0
        self._open = False
        self._lock = RLock()

    @property
    def identity(self) -> StreamIdentity:
        return self._configuration.identity

    @property
    def is_live(self) -> bool:
        return self._is_live

    def open(self) -> None:
        with self._lock:
            self._monitor.record_open_attempt()
            if self._remaining_open_failures:
                self._remaining_open_failures -= 1
                self._monitor.record_fatal_failure(StreamErrorCategory.OPEN)
                raise StreamOpenError("Synthetic camera source could not open.")
            self._open = True
            self._monitor.record_open_success()

    def read(self) -> StreamReadResult:
        with self._lock:
            if not self._open:
                return StreamReadResult(StreamReadStatus.STOPPED)
            if self._cursor >= len(self._events):
                return StreamReadResult(StreamReadStatus.END_OF_STREAM)
            event = self._events[self._cursor]
            self._cursor += 1
            if event.event_type is SyntheticEventType.FRAME:
                payload = FramePayload(
                    bytes([event.marker])
                    * (self._dimensions.width * self._dimensions.height * self._dimensions.channels)
                )
                source_frame = SourceFrame(
                    self._dimensions,
                    payload,
                    source_timestamp_seconds=self._frame_index * self._interval,
                )
                self._frame_index += 1
                self._monitor.record_frame(self._dimensions, at_monotonic=float(self._clock()))
                return StreamReadResult(StreamReadStatus.FRAME, source_frame)
            if event.event_type is SyntheticEventType.TEMPORARY_FAILURE:
                self._monitor.record_temporary_failure()
                return StreamReadResult(
                    StreamReadStatus.TEMPORARY_UNAVAILABLE,
                    retry_after_seconds=float(event.retry_after_seconds),
                )
            if event.event_type is SyntheticEventType.INTERRUPTION:
                self._open = False
                self._monitor.record_temporary_failure(StreamErrorCategory.INTERRUPTED)
                return StreamReadResult(StreamReadStatus.INTERRUPTED)
            if event.event_type is SyntheticEventType.FATAL_FAILURE:
                self._monitor.record_fatal_failure(StreamErrorCategory.READ)
                raise StreamFatalReadError(
                    "Synthetic camera source encountered a fatal read failure."
                )
            if event.event_type is SyntheticEventType.STOPPED:
                self._open = False
                return StreamReadResult(StreamReadStatus.STOPPED)
            return StreamReadResult(StreamReadStatus.END_OF_STREAM)

    def close(self) -> None:
        with self._lock:
            self._open = False
            if self._monitor.health().state is not StreamHealthState.FAILED:
                self._monitor.transition(StreamHealthState.STOPPED)

    def is_open(self) -> bool:
        with self._lock:
            return self._open

    def health(self) -> StreamHealth:
        return self._monitor.health()

    def statistics(self) -> StreamStatistics:
        return self._monitor.statistics()

    def __enter__(self) -> SyntheticCameraSource:
        self.open()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()


__all__ = [
    "SyntheticCameraSource",
    "SyntheticEvent",
    "SyntheticEventType",
    "synthetic_frame_events",
]
