from __future__ import annotations

from datetime import datetime, timezone
from threading import Event
from time import monotonic, sleep

from _phase7_helpers import crossing_event, crossing_result

from hogflow.bootstrap import (
    DEFAULT_CAMERA_CROSSING_CONFIGURATION,
    OPERATOR_LANE_SOURCE_ID,
)
from hogflow.camera import CountingPipelineController, CountingPipelineStatus
from hogflow.counting import LiveCrossingDirection, LiveCrossingResult
from hogflow.streaming import (
    CameraSource,
    FrameDimensions,
    FramePacket,
    SourceType,
    StreamConfiguration,
    StreamIdentity,
    StreamReadResult,
    StreamReadStatus,
    SyntheticCameraSource,
    SyntheticEvent,
    SyntheticEventType,
)


class RecordingSource:
    def __init__(
        self,
        *,
        events: tuple[SyntheticEvent, ...],
        stream_id: str = OPERATOR_LANE_SOURCE_ID,
    ) -> None:
        self.inner = SyntheticCameraSource(
            stream_id=stream_id,
            events=events,
            dimensions=FrameDimensions(8, 6, 3),
            frame_interval_seconds=0,
        )
        self.open_calls = 0
        self.close_calls = 0

    @property
    def identity(self):
        return self.inner.identity

    @property
    def is_live(self) -> bool:
        return self.inner.is_live

    def open(self) -> None:
        self.open_calls += 1
        self.inner.open()

    def read(self):
        return self.inner.read()

    def close(self) -> None:
        if self.inner.is_open():
            self.close_calls += 1
        self.inner.close()

    def is_open(self) -> bool:
        return self.inner.is_open()

    def health(self):
        return self.inner.health()

    def statistics(self):
        return self.inner.statistics()


class BlockingSource:
    def __init__(self, stream_id: str = OPERATOR_LANE_SOURCE_ID) -> None:
        self._identity = StreamIdentity(stream_id, SourceType.USB, "USB camera")
        self._open = False
        self.read_entered = Event()
        self.released = Event()
        self.open_calls = 0
        self.close_calls = 0

    @property
    def identity(self) -> StreamIdentity:
        return self._identity

    @property
    def is_live(self) -> bool:
        return True

    def open(self) -> None:
        self._open = True
        self.open_calls += 1

    def read(self) -> StreamReadResult:
        self.read_entered.set()
        self.released.wait(2)
        return StreamReadResult(StreamReadStatus.STOPPED)

    def close(self) -> None:
        if self._open:
            self.close_calls += 1
        self._open = False
        self.released.set()

    def is_open(self) -> bool:
        return self._open

    def health(self):
        raise NotImplementedError

    def statistics(self):
        raise NotImplementedError


class ScriptedCrossingProcessor:
    def __init__(
        self,
        *,
        event_sequences: tuple[int, ...] = (),
        tracker_id: int = 42,
        entered: Event | None = None,
        release: Event | None = None,
    ) -> None:
        self.event_sequences = frozenset(event_sequences)
        self.tracker_id = tracker_id
        self.entered = entered
        self.release = release
        self.source_id: str | None = None
        self.started = 0
        self.closed = 0
        self.processed: list[tuple[int, str | None]] = []

    @property
    def is_started(self) -> bool:
        return self.source_id is not None

    def start(self, source_id: str) -> None:
        self.source_id = source_id
        self.started += 1

    def process(
        self,
        frame: FramePacket,
        crossing_lifecycle_id: str | None,
    ) -> LiveCrossingResult | None:
        self.processed.append((frame.sequence_number, crossing_lifecycle_id))
        if self.entered is not None and frame.sequence_number == 1:
            self.entered.set()
            assert self.release is not None
            self.release.wait(2)
        if crossing_lifecycle_id is None:
            return None
        events = ()
        if frame.sequence_number in self.event_sequences:
            events = (
                crossing_event(
                    frame.sequence_number,
                    self.tracker_id,
                    LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
                    source_id=frame.stream.stream_id,
                    lifecycle_id=crossing_lifecycle_id,
                    captured_at=frame.timestamp.acquired_at,
                    crossing_fingerprint=DEFAULT_CAMERA_CROSSING_CONFIGURATION.fingerprint,
                    line_id="line-camera-integration",
                ),
            )
        return crossing_result(
            frame.sequence_number,
            events,
            source_id=frame.stream.stream_id,
            lifecycle_id=crossing_lifecycle_id,
            captured_at=frame.timestamp.acquired_at,
            crossing_fingerprint=DEFAULT_CAMERA_CROSSING_CONFIGURATION.fingerprint,
            line_id="line-camera-integration",
        )

    def close(self) -> None:
        if self.source_id is not None:
            self.closed += 1
        self.source_id = None


def finite_events(frame_count: int = 3) -> tuple[SyntheticEvent, ...]:
    return tuple(
        SyntheticEvent(SyntheticEventType.FRAME, marker=index) for index in range(frame_count)
    ) + (SyntheticEvent(SyntheticEventType.END_OF_STREAM),)


def fatal_events() -> tuple[SyntheticEvent, ...]:
    return (
        SyntheticEvent(SyntheticEventType.FRAME, marker=1),
        SyntheticEvent(SyntheticEventType.FATAL_FAILURE),
    )


def source_configuration() -> StreamConfiguration:
    return StreamConfiguration.usb(OPERATOR_LANE_SOURCE_ID, 0)


def wait_for_status(
    controller: CountingPipelineController,
    status: CountingPipelineStatus,
    *,
    timeout: float = 2.0,
) -> None:
    deadline = monotonic() + timeout
    while monotonic() < deadline:
        if controller.snapshot().status is status:
            return
        sleep(0.005)
    raise AssertionError(f"Pipeline did not reach {status.value}: {controller.snapshot()!r}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "CameraSource",
    "BlockingSource",
    "RecordingSource",
    "ScriptedCrossingProcessor",
    "fatal_events",
    "finite_events",
    "source_configuration",
    "utc_now",
    "wait_for_status",
]
