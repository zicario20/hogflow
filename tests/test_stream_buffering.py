from datetime import datetime, timezone
from threading import Thread
from time import sleep

import pytest

from hogflow.streaming.buffering import BoundedFrameBuffer
from hogflow.streaming.configuration import BufferConfiguration, StreamConfiguration
from hogflow.streaming.errors import BufferClosedError
from hogflow.streaming.models import (
    BufferReadStatus,
    FrameDimensions,
    FramePacket,
    FramePayload,
    FrameTimestamp,
    OverflowPolicy,
)


def _packet(sequence_number: int) -> FramePacket:
    return FramePacket(
        stream=StreamConfiguration.synthetic("buffer-test").identity,
        sequence_number=sequence_number,
        timestamp=FrameTimestamp(datetime.now(timezone.utc), float(sequence_number)),
        dimensions=FrameDimensions(1, 1, 3),
        payload=FramePayload(bytes((sequence_number % 256, 0, 0))),
    )


def test_drop_oldest_retains_most_recent_frames_and_records_gap() -> None:
    buffer = BoundedFrameBuffer(BufferConfiguration(2, OverflowPolicy.DROP_OLDEST))
    for sequence in range(4):
        assert buffer.submit(_packet(sequence))

    first = buffer.get(0)
    second = buffer.get(0)
    statistics = buffer.statistics()

    assert first.frame is not None and first.frame.sequence_number == 2
    assert first.frame.dropped_since_previous == 2
    assert second.frame is not None and second.frame.sequence_number == 3
    assert statistics.frames_dropped == 2
    assert statistics.maximum_observed_depth == 2


def test_drop_newest_rejects_arrival_without_reordering_queue() -> None:
    buffer = BoundedFrameBuffer(BufferConfiguration(2, OverflowPolicy.DROP_NEWEST))
    assert buffer.submit(_packet(0))
    assert buffer.submit(_packet(1))
    assert not buffer.submit(_packet(2))

    assert [buffer.get(0).frame.sequence_number for _ in range(2)] == [0, 1]  # type: ignore[union-attr]
    assert buffer.statistics().frames_dropped == 1


def test_slow_consumer_cannot_cause_unbounded_growth() -> None:
    buffer = BoundedFrameBuffer(BufferConfiguration(3))
    for sequence in range(1_000):
        buffer.submit(_packet(sequence))

    statistics = buffer.statistics()
    assert statistics.current_depth == 3
    assert statistics.maximum_observed_depth == 3
    assert statistics.frames_dropped == 997


def test_timeout_is_explicit() -> None:
    result = BoundedFrameBuffer().get(0.001)

    assert result.status is BufferReadStatus.TIMEOUT
    assert result.frame is None


def test_shutdown_unblocks_waiting_consumer() -> None:
    buffer = BoundedFrameBuffer()
    results = []
    thread = Thread(target=lambda: results.append(buffer.get(None)))
    thread.start()
    sleep(0.01)

    buffer.close()
    thread.join(1)

    assert not thread.is_alive()
    assert results[0].status is BufferReadStatus.CLOSED


def test_pending_frames_can_be_drained_after_close() -> None:
    buffer = BoundedFrameBuffer()
    buffer.submit(_packet(0))
    buffer.close()

    assert buffer.get(0).status is BufferReadStatus.FRAME
    assert buffer.get(0).status is BufferReadStatus.CLOSED


def test_submit_after_close_is_rejected() -> None:
    buffer = BoundedFrameBuffer()
    buffer.close()

    with pytest.raises(BufferClosedError):
        buffer.submit(_packet(0))
