import pytest

from hogflow.streaming.configuration import StreamConfiguration
from hogflow.streaming.health import StreamHealthMonitor
from hogflow.streaming.models import (
    FrameDimensions,
    StreamErrorCategory,
    StreamHealthState,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_health_state_transitions_and_statistics() -> None:
    clock = FakeClock()
    monitor = StreamHealthMonitor(
        StreamConfiguration.synthetic("health").identity,
        monotonic_clock=clock,
    )
    monitor.record_open_attempt()
    monitor.record_open_success()
    monitor.record_frame(FrameDimensions(10, 8), sequence_number=0)
    clock.advance(0.5)
    monitor.record_frame(FrameDimensions(10, 8), sequence_number=1)

    health = monitor.health()
    statistics = monitor.statistics()

    assert health.state is StreamHealthState.RUNNING
    assert health.observed_fps == pytest.approx(2.0)
    assert statistics.average_acquisition_interval_seconds == pytest.approx(0.5)
    assert statistics.frames_acquired == 2
    assert statistics.last_frame_sequence_number == 1


def test_fps_counts_zero_duration_intervals_from_quantized_clock() -> None:
    clock = FakeClock()
    monitor = StreamHealthMonitor(
        StreamConfiguration.synthetic("health").identity,
        monotonic_clock=clock,
    )
    dimensions = FrameDimensions(10, 8)
    monitor.record_frame(dimensions)
    monitor.record_frame(dimensions)
    clock.advance(0.5)
    monitor.record_frame(dimensions)

    statistics = monitor.statistics()

    assert statistics.average_acquisition_interval_seconds == pytest.approx(0.25)
    assert statistics.observed_fps == pytest.approx(4.0)


def test_temporary_failure_and_recovery_reset_consecutive_count() -> None:
    monitor = StreamHealthMonitor(StreamConfiguration.synthetic("health").identity)

    assert monitor.record_temporary_failure() == 1
    assert monitor.health().state is StreamHealthState.DEGRADED
    monitor.record_frame(FrameDimensions(1, 1))

    assert monitor.health().consecutive_read_failures == 0
    assert monitor.health().last_error_category is StreamErrorCategory.NONE


def test_health_retains_only_category_not_error_message() -> None:
    monitor = StreamHealthMonitor(StreamConfiguration.synthetic("health").identity)
    monitor.record_fatal_failure(StreamErrorCategory.READ)

    rendered = repr(monitor.health())
    assert monitor.health().last_error_category is StreamErrorCategory.READ
    assert "rtsp" not in rendered.lower()
    assert "password" not in rendered.lower()
