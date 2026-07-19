from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from time import monotonic

from hogflow.streaming.models import (
    BufferReadResult,
    BufferReadStatus,
    FrameDimensions,
    FramePacket,
    FramePayload,
    FrameTimestamp,
    SourceType,
    StreamHealth,
    StreamHealthState,
    StreamIdentity,
    StreamStatistics,
)


def frame_packet(
    sequence: int,
    *,
    stream_id: str = "camera",
    monotonic_seconds: float | None = None,
    width: int = 8,
    height: int = 6,
) -> FramePacket:
    dimensions = FrameDimensions(width, height, 3)
    return FramePacket(
        stream=StreamIdentity(stream_id, SourceType.SYNTHETIC, "synthetic-camera"),
        sequence_number=sequence,
        timestamp=FrameTimestamp(
            acquired_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
            monotonic_seconds=(monotonic() if monotonic_seconds is None else monotonic_seconds),
            source_seconds=sequence / 10,
        ),
        dimensions=dimensions,
        payload=FramePayload(bytes([sequence % 256]) * (width * height * 3)),
    )


def scripted_reads(*items: FramePacket | BufferReadStatus | BaseException) -> tuple[object, ...]:
    values: list[object] = []
    for item in items:
        if isinstance(item, FramePacket):
            values.append(BufferReadResult(BufferReadStatus.FRAME, item))
        elif isinstance(item, BufferReadStatus):
            values.append(BufferReadResult(item))
        else:
            values.append(item)
    return tuple(values)


class ScriptedBuffer:
    def __init__(self, reads: tuple[object, ...]) -> None:
        self._reads = deque(reads)

    def get(self, _timeout_seconds: float | None = None) -> BufferReadResult:
        if not self._reads:
            return BufferReadResult(BufferReadStatus.CLOSED)
        value = self._reads.popleft()
        if isinstance(value, BaseException):
            raise value
        assert isinstance(value, BufferReadResult)
        return value


class StubStreamRunner:
    def __init__(
        self,
        reads: tuple[object, ...],
        *,
        frames_acquired: int,
        frames_dropped: int = 0,
        observed_fps: float = 30.0,
    ) -> None:
        self.buffer = ScriptedBuffer(reads)
        self.identity = StreamIdentity("camera", SourceType.SYNTHETIC, "synthetic-camera")
        self._frames_acquired = frames_acquired
        self._frames_dropped = frames_dropped
        self._observed_fps = observed_fps
        self.started = False
        self.stopped = False
        self.joined = False
        self._source_open = False

    def start(self) -> None:
        self.started = True
        self._source_open = True

    def stop(self) -> None:
        self.stopped = True
        self._source_open = False

    def join(self, _timeout: float | None = None, *, raise_on_failure: bool = False) -> bool:
        del raise_on_failure
        self.joined = True
        return True

    def health(self) -> StreamHealth:
        return StreamHealth(
            identity=self.identity,
            state=StreamHealthState.STOPPED if self.stopped else StreamHealthState.RUNNING,
            observed_dimensions=FrameDimensions(8, 6, 3),
            observed_fps=self._observed_fps,
        )

    def statistics(self) -> StreamStatistics:
        return StreamStatistics(
            open_attempts=1,
            successful_opens=1,
            frames_acquired=self._frames_acquired,
            frames_submitted=self._frames_acquired,
            frames_dropped=self._frames_dropped,
            observed_fps=self._observed_fps,
            runtime_seconds=1.0,
        )

    def source_is_open(self) -> bool:
        return self._source_open
