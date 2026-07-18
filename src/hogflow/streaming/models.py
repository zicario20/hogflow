"""Immutable framework-neutral models for continuous frame acquisition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from re import fullmatch

from hogflow.core import InputDataError


class SourceType(str, Enum):
    """Explicit camera-source categories supported by Phase 5.1."""

    USB = "usb"
    RTSP = "rtsp"
    FILE = "file"
    SYNTHETIC = "synthetic"


class PixelFormat(str, Enum):
    """Framework-neutral pixel layouts accepted by ``FramePayload``."""

    RGB24 = "rgb24"


class StreamHealthState(str, Enum):
    """Bounded lifecycle states exposed by stream health reports."""

    CREATED = "created"
    OPENING = "opening"
    WARMING_UP = "warming_up"
    RUNNING = "running"
    DEGRADED = "degraded"
    RECONNECTING = "reconnecting"
    STOPPED = "stopped"
    FAILED = "failed"


class StreamErrorCategory(str, Enum):
    """Sanitized error categories that never contain source details."""

    NONE = "none"
    CONFIGURATION = "configuration"
    DEPENDENCY = "dependency"
    OPEN = "open"
    READ = "read"
    INTERRUPTED = "interrupted"
    INTERNAL = "internal"


class StreamReadStatus(str, Enum):
    """Explicit outcomes from one source read operation."""

    FRAME = "frame"
    TEMPORARY_UNAVAILABLE = "temporary_unavailable"
    END_OF_STREAM = "end_of_stream"
    INTERRUPTED = "interrupted"
    STOPPED = "stopped"


class OverflowPolicy(str, Enum):
    """Deterministic behavior when a bounded buffer is full."""

    DROP_OLDEST = "drop_oldest"
    DROP_NEWEST = "drop_newest"


class BufferReadStatus(str, Enum):
    """Explicit outcomes from a bounded-buffer retrieval."""

    FRAME = "frame"
    TIMEOUT = "timeout"
    CLOSED = "closed"


def _integer(value: object, *, name: str, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise InputDataError(f"{name} must be an integer greater than or equal to {minimum}.")
    return value


def _finite(value: object, *, name: str, minimum: float = 0.0) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or float(value) < minimum
    ):
        raise InputDataError(f"{name} must be finite and greater than or equal to {minimum}.")
    return float(value)


@dataclass(frozen=True, slots=True)
class FrameDimensions:
    """Positive frame width, height, and channel count."""

    width: int
    height: int
    channels: int = 3

    def __post_init__(self) -> None:
        _integer(self.width, name="Frame width", minimum=1)
        _integer(self.height, name="Frame height", minimum=1)
        _integer(self.channels, name="Frame channel count", minimum=1)


@dataclass(frozen=True, slots=True)
class FramePayload:
    """Caller-owned immutable pixels with no framework-specific object.

    Phase 5.1 uses packed row-major RGB bytes. Adapters must copy mutable
    framework frames into this payload before returning. Consumers may safely
    retain the bytes, and no producer may mutate them after delivery.
    """

    data: bytes
    pixel_format: PixelFormat = PixelFormat.RGB24

    def __post_init__(self) -> None:
        if not isinstance(self.data, bytes):
            raise InputDataError("Frame payload data must be immutable bytes.")
        if not isinstance(self.pixel_format, PixelFormat):
            raise InputDataError("Frame payload pixel_format must be a PixelFormat.")

    def validate_dimensions(self, dimensions: FrameDimensions) -> None:
        """Validate packed payload length against its accompanying dimensions."""

        if not isinstance(dimensions, FrameDimensions):
            raise InputDataError("Frame payload dimensions must be FrameDimensions.")
        if self.pixel_format is PixelFormat.RGB24:
            if dimensions.channels != 3:
                raise InputDataError("RGB24 payloads require exactly three channels.")
            expected = dimensions.width * dimensions.height * dimensions.channels
            if len(self.data) != expected:
                raise InputDataError(
                    f"RGB24 payload must contain exactly {expected} bytes for its dimensions."
                )


@dataclass(frozen=True, slots=True)
class FrameTimestamp:
    """Wall, monotonic, and optional source time for one acquired frame.

    ``monotonic_seconds`` is the ordering and duration clock. Wall-clock time
    is informational only and must not be used to order packets.
    """

    acquired_at: datetime
    monotonic_seconds: float
    source_seconds: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.acquired_at, datetime) or self.acquired_at.tzinfo is None:
            raise InputDataError("Frame acquisition time must be a timezone-aware datetime.")
        _finite(self.monotonic_seconds, name="Frame monotonic timestamp")
        if self.source_seconds is not None:
            _finite(self.source_seconds, name="Frame source timestamp")


@dataclass(frozen=True, slots=True)
class StreamIdentity:
    """Opaque, sanitized identity safe for logs, health, and ``repr``."""

    stream_id: str
    source_type: SourceType
    display_name: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.stream_id, str)
            or fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", self.stream_id) is None
        ):
            raise InputDataError("Stream ID must be an opaque identifier of at most 64 characters.")
        if not isinstance(self.source_type, SourceType):
            raise InputDataError("Stream source type must be explicit.")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise InputDataError("Sanitized stream display name must be non-empty text.")
        forbidden = ("@", "://", "\\", "/", "password", "credential")
        lowered = self.display_name.lower()
        if any(token in lowered for token in forbidden):
            raise InputDataError("Stream display name contains unsafe source material.")


@dataclass(frozen=True, slots=True)
class SourceFrame:
    """One framework-neutral frame returned by a concrete source adapter."""

    dimensions: FrameDimensions
    payload: FramePayload
    source_timestamp_seconds: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dimensions, FrameDimensions):
            raise InputDataError("Source frame dimensions must be FrameDimensions.")
        if not isinstance(self.payload, FramePayload):
            raise InputDataError("Source frame payload must be FramePayload.")
        self.payload.validate_dimensions(self.dimensions)
        if self.source_timestamp_seconds is not None:
            _finite(self.source_timestamp_seconds, name="Source frame timestamp")


@dataclass(frozen=True, slots=True)
class FramePacket:
    """One ordered live-stream packet delivered to future consumers."""

    stream: StreamIdentity
    sequence_number: int
    timestamp: FrameTimestamp
    dimensions: FrameDimensions
    payload: FramePayload
    dropped_since_previous: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.stream, StreamIdentity):
            raise InputDataError("Frame packet stream must be StreamIdentity.")
        _integer(self.sequence_number, name="Frame sequence number")
        if not isinstance(self.timestamp, FrameTimestamp):
            raise InputDataError("Frame packet timestamp must be FrameTimestamp.")
        if not isinstance(self.dimensions, FrameDimensions):
            raise InputDataError("Frame packet dimensions must be FrameDimensions.")
        if not isinstance(self.payload, FramePayload):
            raise InputDataError("Frame packet payload must be FramePayload.")
        self.payload.validate_dimensions(self.dimensions)
        _integer(self.dropped_since_previous, name="Dropped-frame count")


@dataclass(frozen=True, slots=True)
class StreamReadResult:
    """An explicit source read outcome; fatal failures use stream exceptions."""

    status: StreamReadStatus
    frame: SourceFrame | None = None
    retry_after_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not isinstance(self.status, StreamReadStatus):
            raise InputDataError("Read status must be StreamReadStatus.")
        if self.status is StreamReadStatus.FRAME:
            if not isinstance(self.frame, SourceFrame):
                raise InputDataError("A successful read result requires a SourceFrame.")
        elif self.frame is not None:
            raise InputDataError("A non-frame read result must not contain a frame.")
        _finite(self.retry_after_seconds, name="Read retry delay")


@dataclass(frozen=True, slots=True)
class StreamHealth:
    """Current bounded health snapshot without source URLs or error text."""

    identity: StreamIdentity
    state: StreamHealthState
    consecutive_read_failures: int = 0
    last_success_monotonic_seconds: float | None = None
    observed_dimensions: FrameDimensions | None = None
    observed_fps: float | None = None
    current_buffer_depth: int = 0
    last_error_category: StreamErrorCategory = StreamErrorCategory.NONE

    def __post_init__(self) -> None:
        if not isinstance(self.identity, StreamIdentity):
            raise InputDataError("Stream health requires a sanitized StreamIdentity.")
        if not isinstance(self.state, StreamHealthState):
            raise InputDataError("Stream health state is invalid.")
        _integer(self.consecutive_read_failures, name="Consecutive read failures")
        if self.last_success_monotonic_seconds is not None:
            _finite(self.last_success_monotonic_seconds, name="Last success timestamp")
        if self.observed_dimensions is not None and not isinstance(
            self.observed_dimensions, FrameDimensions
        ):
            raise InputDataError("Observed dimensions must be FrameDimensions.")
        if self.observed_fps is not None:
            _finite(self.observed_fps, name="Observed FPS")
        _integer(self.current_buffer_depth, name="Current buffer depth")
        if not isinstance(self.last_error_category, StreamErrorCategory):
            raise InputDataError("Last error category is invalid.")


@dataclass(frozen=True, slots=True)
class StreamStatistics:
    """Aggregate source, runner, and buffer counters for one lifecycle."""

    open_attempts: int = 0
    successful_opens: int = 0
    frames_acquired: int = 0
    frames_submitted: int = 0
    frames_delivered: int = 0
    frames_dropped: int = 0
    temporary_read_failures: int = 0
    fatal_read_failures: int = 0
    reconnect_count: int = 0
    current_buffer_depth: int = 0
    maximum_buffer_depth: int = 0
    last_frame_sequence_number: int | None = None
    observed_fps: float | None = None
    average_acquisition_interval_seconds: float | None = None
    runtime_seconds: float = 0.0

    def __post_init__(self) -> None:
        for field_name in (
            "open_attempts",
            "successful_opens",
            "frames_acquired",
            "frames_submitted",
            "frames_delivered",
            "frames_dropped",
            "temporary_read_failures",
            "fatal_read_failures",
            "reconnect_count",
            "current_buffer_depth",
            "maximum_buffer_depth",
        ):
            _integer(getattr(self, field_name), name=field_name)
        if self.last_frame_sequence_number is not None:
            _integer(self.last_frame_sequence_number, name="Last frame sequence number")
        for field_name in ("observed_fps", "average_acquisition_interval_seconds"):
            value = getattr(self, field_name)
            if value is not None:
                _finite(value, name=field_name)
        _finite(self.runtime_seconds, name="Runtime")


@dataclass(frozen=True, slots=True)
class BufferStatistics:
    """Thread-safe bounded-buffer counters returned as one immutable snapshot."""

    capacity: int
    frames_submitted: int
    frames_delivered: int
    frames_dropped: int
    current_depth: int
    maximum_observed_depth: int
    last_frame_sequence_number: int | None
    closed: bool

    def __post_init__(self) -> None:
        _integer(self.capacity, name="Buffer capacity", minimum=1)
        for field_name in (
            "frames_submitted",
            "frames_delivered",
            "frames_dropped",
            "current_depth",
            "maximum_observed_depth",
        ):
            _integer(getattr(self, field_name), name=field_name)
        if self.current_depth > self.capacity or self.maximum_observed_depth > self.capacity:
            raise InputDataError("Buffer depth cannot exceed capacity.")
        if self.last_frame_sequence_number is not None:
            _integer(self.last_frame_sequence_number, name="Last buffer sequence number")
        if not isinstance(self.closed, bool):
            raise InputDataError("Buffer closed state must be boolean.")


@dataclass(frozen=True, slots=True)
class BufferReadResult:
    """An explicit frame, timeout, or closed result from a bounded buffer."""

    status: BufferReadStatus
    frame: FramePacket | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, BufferReadStatus):
            raise InputDataError("Buffer read status is invalid.")
        if self.status is BufferReadStatus.FRAME:
            if not isinstance(self.frame, FramePacket):
                raise InputDataError("A successful buffer read requires a FramePacket.")
        elif self.frame is not None:
            raise InputDataError("A non-frame buffer result must not contain a frame.")


__all__ = [
    "BufferReadResult",
    "BufferReadStatus",
    "BufferStatistics",
    "FrameDimensions",
    "FramePacket",
    "FramePayload",
    "FrameTimestamp",
    "OverflowPolicy",
    "PixelFormat",
    "SourceFrame",
    "SourceType",
    "StreamErrorCategory",
    "StreamHealth",
    "StreamHealthState",
    "StreamIdentity",
    "StreamReadResult",
    "StreamReadStatus",
    "StreamStatistics",
]
