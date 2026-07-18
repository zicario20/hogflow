"""Thread-safe bounded frame buffering with deterministic overflow behavior."""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from threading import Condition
from time import monotonic

from hogflow.core import InputDataError
from hogflow.streaming.configuration import BufferConfiguration
from hogflow.streaming.errors import BufferClosedError
from hogflow.streaming.models import (
    BufferReadResult,
    BufferReadStatus,
    BufferStatistics,
    FramePacket,
    OverflowPolicy,
)


class BoundedFrameBuffer:
    """Hold only a fixed number of recent immutable frame packets.

    ``drop_oldest`` is the real-time default: when downstream work is slower
    than acquisition, the oldest queued packet is discarded so latency remains
    bounded and recent frames remain available. ``drop_newest`` rejects the
    arriving packet instead. Statistics make every drop observable.
    """

    def __init__(self, configuration: BufferConfiguration | None = None) -> None:
        self._configuration = configuration or BufferConfiguration()
        self._frames: deque[FramePacket] = deque()
        self._condition = Condition()
        self._closed = False
        self._submitted = 0
        self._delivered = 0
        self._dropped = 0
        self._maximum_depth = 0
        self._last_sequence: int | None = None
        self._last_delivered_sequence: int | None = None

    @property
    def configuration(self) -> BufferConfiguration:
        """Return the immutable capacity and overflow policy."""

        return self._configuration

    def submit(self, frame: FramePacket) -> bool:
        """Submit a frame and return whether the arriving frame was retained."""

        if not isinstance(frame, FramePacket):
            raise InputDataError("Bounded frame buffer accepts only FramePacket values.")
        with self._condition:
            if self._closed:
                raise BufferClosedError("Frame buffer is closed.")
            self._submitted += 1
            self._last_sequence = frame.sequence_number
            accepted = True
            if len(self._frames) >= self._configuration.capacity:
                self._dropped += 1
                if self._configuration.overflow_policy is OverflowPolicy.DROP_OLDEST:
                    self._frames.popleft()
                else:
                    accepted = False
            if accepted:
                self._frames.append(frame)
                self._maximum_depth = max(self._maximum_depth, len(self._frames))
                self._condition.notify()
            return accepted

    def get(self, timeout_seconds: float | None = None) -> BufferReadResult:
        """Return a frame, timeout, or closed result without ambiguous ``None``."""

        if timeout_seconds is not None and (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or not 0 <= float(timeout_seconds)
        ):
            raise InputDataError("Buffer timeout must be a non-negative number or None.")
        deadline = None if timeout_seconds is None else monotonic() + float(timeout_seconds)
        with self._condition:
            while not self._frames and not self._closed:
                remaining = None if deadline is None else deadline - monotonic()
                if remaining is not None and remaining <= 0:
                    return BufferReadResult(BufferReadStatus.TIMEOUT)
                self._condition.wait(remaining)
            if self._frames:
                self._delivered += 1
                frame = self._frames.popleft()
                expected = (
                    0
                    if self._last_delivered_sequence is None
                    else self._last_delivered_sequence + 1
                )
                sequence_gap = max(0, frame.sequence_number - expected)
                self._last_delivered_sequence = frame.sequence_number
                if frame.dropped_since_previous != sequence_gap:
                    frame = replace(frame, dropped_since_previous=sequence_gap)
                return BufferReadResult(BufferReadStatus.FRAME, frame)
            return BufferReadResult(BufferReadStatus.CLOSED)

    def close(self, *, discard_pending: bool = False) -> None:
        """Close the buffer and unblock all waiting consumers."""

        if not isinstance(discard_pending, bool):
            raise InputDataError("discard_pending must be boolean.")
        with self._condition:
            self._closed = True
            if discard_pending:
                self._dropped += len(self._frames)
                self._frames.clear()
            self._condition.notify_all()

    def statistics(self) -> BufferStatistics:
        """Return one immutable counter snapshot."""

        with self._condition:
            return BufferStatistics(
                capacity=self._configuration.capacity,
                frames_submitted=self._submitted,
                frames_delivered=self._delivered,
                frames_dropped=self._dropped,
                current_depth=len(self._frames),
                maximum_observed_depth=self._maximum_depth,
                last_frame_sequence_number=self._last_sequence,
                closed=self._closed,
            )


__all__ = ["BoundedFrameBuffer"]
