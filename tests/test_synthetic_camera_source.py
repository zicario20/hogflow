import pytest

from hogflow.streaming.errors import StreamFatalReadError, StreamOpenError
from hogflow.streaming.models import (
    FrameDimensions,
    StreamHealthState,
    StreamReadStatus,
)
from hogflow.streaming.synthetic import (
    SyntheticCameraSource,
    SyntheticEvent,
    SyntheticEventType,
)


def test_deterministic_synthetic_source_lifecycle_and_payload_markers() -> None:
    source = SyntheticCameraSource(frame_count=2, dimensions=FrameDimensions(2, 1, 3))

    source.open()
    first = source.read()
    second = source.read()
    end = source.read()
    source.close()

    assert first.status is StreamReadStatus.FRAME
    assert second.status is StreamReadStatus.FRAME
    assert end.status is StreamReadStatus.END_OF_STREAM
    assert first.frame is not None and first.frame.payload.data == bytes(6)
    assert second.frame is not None and second.frame.payload.data == bytes([1]) * 6
    assert (first.frame.source_timestamp_seconds, second.frame.source_timestamp_seconds) == (
        0.0,
        0.1,
    )
    assert source.statistics().frames_acquired == 2
    assert source.health().state is StreamHealthState.STOPPED


def test_source_open_failure_is_sanitized_and_recoverable() -> None:
    source = SyntheticCameraSource(frame_count=1, open_failures=1)

    with pytest.raises(StreamOpenError, match="Synthetic camera source"):
        source.open()
    source.open()

    assert source.is_open()
    source.close()


def test_temporary_failure_is_explicit_and_does_not_close_source() -> None:
    source = SyntheticCameraSource(
        events=(
            SyntheticEvent(SyntheticEventType.TEMPORARY_FAILURE, retry_after_seconds=0.2),
            SyntheticEvent(SyntheticEventType.FRAME, marker=7),
        )
    )
    source.open()

    unavailable = source.read()
    frame = source.read()

    assert unavailable.status is StreamReadStatus.TEMPORARY_UNAVAILABLE
    assert unavailable.retry_after_seconds == 0.2
    assert frame.status is StreamReadStatus.FRAME
    assert source.is_open()


def test_interruption_requires_reopen_and_continues_script() -> None:
    source = SyntheticCameraSource(
        is_live=True,
        events=(
            SyntheticEvent(SyntheticEventType.INTERRUPTION),
            SyntheticEvent(SyntheticEventType.FRAME, marker=9),
        ),
    )
    source.open()

    assert source.read().status is StreamReadStatus.INTERRUPTED
    assert not source.is_open()
    source.open()
    assert source.read().status is StreamReadStatus.FRAME


def test_fatal_failure_raises_without_framework_or_source_details() -> None:
    source = SyntheticCameraSource(events=(SyntheticEvent(SyntheticEventType.FATAL_FAILURE),))
    source.open()

    with pytest.raises(StreamFatalReadError, match="fatal read failure"):
        source.read()


def test_context_manager_closes_source() -> None:
    source = SyntheticCameraSource(frame_count=1)

    with source:
        assert source.is_open()

    assert not source.is_open()
