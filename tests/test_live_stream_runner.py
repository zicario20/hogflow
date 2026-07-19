from datetime import datetime, timezone
from threading import Event, get_ident

from hogflow.streaming.buffering import BoundedFrameBuffer
from hogflow.streaming.configuration import (
    BufferConfiguration,
    ReconnectPolicy,
    StreamConfiguration,
)
from hogflow.streaming.lifecycle import LiveStreamRunner
from hogflow.streaming.models import (
    BufferReadStatus,
    OverflowPolicy,
    StreamHealthState,
    StreamReadResult,
)
from hogflow.streaming.synthetic import (
    SyntheticCameraSource,
    SyntheticEvent,
    SyntheticEventType,
)


class SteppingClock:
    def __init__(self, step: float = 0.1) -> None:
        self.value = 0.0
        self.step = step

    def __call__(self) -> float:
        current = self.value
        self.value += self.step
        return current


class ControlledReadSyntheticSource(SyntheticCameraSource):
    def __init__(self) -> None:
        super().__init__(frame_count=1)
        self.read_started = Event()
        self.release_read = Event()
        self.close_thread_ids: list[int] = []

    def read(self) -> StreamReadResult:
        self.read_started.set()
        self.release_read.wait(2.0)
        return super().read()

    def close(self) -> None:
        self.close_thread_ids.append(get_ident())
        self.release_read.set()
        super().close()


def _runner(
    source: SyntheticCameraSource,
    *,
    capacity: int = 20,
    reconnect: ReconnectPolicy | None = None,
    configuration: StreamConfiguration | None = None,
    sleeps: list[float] | None = None,
) -> LiveStreamRunner:
    clock = SteppingClock()
    return LiveStreamRunner(
        source,
        BoundedFrameBuffer(BufferConfiguration(capacity, OverflowPolicy.DROP_OLDEST)),
        configuration or StreamConfiguration.synthetic(source.identity.stream_id),
        reconnect or ReconnectPolicy(enabled=False),
        monotonic_clock=clock,
        wall_clock=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        sleeper=(sleeps.append if sleeps is not None else lambda _seconds: None),
    )


def _drain_sequences(runner: LiveStreamRunner) -> list[int]:
    sequences: list[int] = []
    while True:
        result = runner.buffer.get(0)
        if result.status is BufferReadStatus.CLOSED:
            return sequences
        if result.status is BufferReadStatus.FRAME and result.frame is not None:
            sequences.append(result.frame.sequence_number)


def test_runner_assigns_monotonically_increasing_sequences_and_closes() -> None:
    source = SyntheticCameraSource(frame_count=5)
    runner = _runner(source)

    runner.run()

    assert _drain_sequences(runner) == [0, 1, 2, 3, 4]
    assert runner.statistics().frames_acquired == 5
    assert runner.health().state is StreamHealthState.STOPPED
    assert not source.is_open()


def test_live_source_reconnects_after_interruption_without_resetting_sequence() -> None:
    source = SyntheticCameraSource(
        is_live=True,
        events=(
            SyntheticEvent(SyntheticEventType.FRAME, marker=1),
            SyntheticEvent(SyntheticEventType.INTERRUPTION),
            SyntheticEvent(SyntheticEventType.FRAME, marker=2),
            SyntheticEvent(SyntheticEventType.STOPPED),
        ),
    )
    sleeps: list[float] = []
    runner = _runner(
        source,
        reconnect=ReconnectPolicy(initial_delay_seconds=0.25, maximum_attempts=3),
        sleeps=sleeps,
    )

    runner.run()

    assert _drain_sequences(runner) == [0, 1]
    assert runner.statistics().reconnect_count == 1
    assert sleeps == [0.25]


def test_reconnect_backoff_handles_temporary_open_unavailability() -> None:
    source = SyntheticCameraSource(
        is_live=True,
        open_failures=2,
        events=(SyntheticEvent(SyntheticEventType.STOPPED),),
    )
    sleeps: list[float] = []
    runner = _runner(
        source,
        reconnect=ReconnectPolicy(
            initial_delay_seconds=0.5,
            maximum_delay_seconds=2.0,
            maximum_attempts=3,
        ),
        sleeps=sleeps,
    )

    runner.run()

    assert sleeps == [0.5, 1.0]
    assert runner.statistics().open_attempts == 3
    assert runner.statistics().successful_opens == 1


def test_reconnect_attempt_backoff_resets_after_stable_operation() -> None:
    source = SyntheticCameraSource(
        is_live=True,
        events=(
            SyntheticEvent(SyntheticEventType.INTERRUPTION),
            SyntheticEvent(SyntheticEventType.FRAME),
            SyntheticEvent(SyntheticEventType.INTERRUPTION),
            SyntheticEvent(SyntheticEventType.FRAME),
            SyntheticEvent(SyntheticEventType.STOPPED),
        ),
    )
    sleeps: list[float] = []
    runner = _runner(
        source,
        reconnect=ReconnectPolicy(
            initial_delay_seconds=0.25,
            maximum_attempts=3,
            reset_after_stable_seconds=0.0,
        ),
        sleeps=sleeps,
    )

    runner.run()

    assert sleeps == [0.25, 0.25]
    assert runner.statistics().reconnect_count == 2


def test_reconnect_maximum_attempts_ends_in_failed_health() -> None:
    source = SyntheticCameraSource(is_live=True, open_failures=10)
    sleeps: list[float] = []
    runner = _runner(
        source,
        reconnect=ReconnectPolicy(maximum_attempts=2),
        sleeps=sleeps,
    )

    runner.run()

    assert runner.statistics().reconnect_count == 2
    assert runner.statistics().open_attempts == 3
    assert runner.health().state is StreamHealthState.FAILED


def test_temporary_read_failure_retries_without_reconnect_below_limit() -> None:
    source = SyntheticCameraSource(
        is_live=True,
        events=(
            SyntheticEvent(SyntheticEventType.TEMPORARY_FAILURE, retry_after_seconds=0.2),
            SyntheticEvent(SyntheticEventType.FRAME),
            SyntheticEvent(SyntheticEventType.STOPPED),
        ),
    )
    sleeps: list[float] = []
    runner = _runner(source, sleeps=sleeps)

    runner.run()

    assert runner.statistics().temporary_read_failures == 1
    assert runner.statistics().reconnect_count == 0
    assert sleeps == [0.2]


def test_fatal_live_read_reconnects_and_closes_resources() -> None:
    source = SyntheticCameraSource(
        is_live=True,
        events=(
            SyntheticEvent(SyntheticEventType.FATAL_FAILURE),
            SyntheticEvent(SyntheticEventType.FRAME),
            SyntheticEvent(SyntheticEventType.STOPPED),
        ),
    )
    runner = _runner(source, reconnect=ReconnectPolicy(maximum_attempts=2))

    runner.run()

    assert runner.statistics().fatal_read_failures == 1
    assert runner.statistics().reconnect_count == 1
    assert _drain_sequences(runner) == [0]
    assert not source.is_open()


def test_background_runner_stop_unblocks_consumer_and_closes_source() -> None:
    source = SyntheticCameraSource(frame_count=1_000)
    runner = _runner(source, capacity=2)

    runner.start()
    runner.stop()

    assert runner.join(2.0)
    assert not source.is_open()
    assert runner.buffer.statistics().closed


def test_background_stop_releases_cooperatively_on_producer_thread() -> None:
    source = ControlledReadSyntheticSource()
    runner = _runner(source)
    caller_thread_id = get_ident()
    runner.start()
    assert source.read_started.wait(1.0)

    runner.stop()
    assert source.is_open()
    source.release_read.set()

    assert runner.join(2.0, raise_on_failure=True)
    assert not source.is_open()
    assert caller_thread_id not in source.close_thread_ids


def test_join_forces_close_when_source_read_remains_blocked() -> None:
    source = ControlledReadSyntheticSource()
    runner = _runner(source)
    caller_thread_id = get_ident()
    runner.start()
    assert source.read_started.wait(1.0)

    runner.stop()

    assert runner.join(2.0, raise_on_failure=True)
    assert not source.is_open()
    assert caller_thread_id in source.close_thread_ids


def test_synthetic_end_to_end_prioritizes_bounded_latency_for_slow_consumer() -> None:
    source = SyntheticCameraSource(frame_count=50)
    runner = _runner(source, capacity=4)

    runner.run()
    sequences = _drain_sequences(runner)
    statistics = runner.statistics()

    assert sequences == [46, 47, 48, 49]
    assert statistics.maximum_buffer_depth == 4
    assert statistics.frames_dropped == 46
    assert statistics.frames_acquired == 50
    assert runner.health().state is StreamHealthState.STOPPED
