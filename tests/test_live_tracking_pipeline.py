from __future__ import annotations

from dataclasses import replace

import pytest
from _phase5_2_helpers import StubStreamRunner, frame_packet, scripted_reads
from _phase5_3_helpers import pig_detection

from hogflow.detection import (
    EmptyDetector,
    FailingDetector,
    PreviewAction,
    ScriptedDetector,
    SlowDetector,
    SyntheticMovingBoxDetector,
)
from hogflow.detection.errors import FatalInferenceError
from hogflow.pipeline import LiveTrackingPipeline
from hogflow.streaming import (
    BoundedFrameBuffer,
    BufferConfiguration,
    LiveStreamRunner,
    OverflowPolicy,
    ReconnectPolicy,
    StreamConfiguration,
    SyntheticCameraSource,
)
from hogflow.streaming.models import BufferReadStatus
from hogflow.tracking import (
    DeterministicIoUTracker,
    EmptyTracker,
    FailingTracker,
    FatalTrackingError,
    TrackingPreviewError,
)


def _runner_for_batches(*batches: tuple[int, ...], reconnects: int = 0) -> StubStreamRunner:
    reads: list[object] = []
    total = 0
    for batch in batches:
        reads.extend(frame_packet(sequence) for sequence in batch)
        reads.append(BufferReadStatus.TIMEOUT)
        total += len(batch)
    reads.append(BufferReadStatus.CLOSED)
    runner = StubStreamRunner(scripted_reads(*reads), frames_acquired=total)
    if reconnects:
        original = runner.statistics
        runner.statistics = lambda: replace(original(), reconnect_count=reconnects)  # type: ignore[method-assign]
    return runner


class TrackingPreviewDouble:
    def __init__(self, *, fail: bool = False, stop: bool = False) -> None:
        self.fail = fail
        self.stop = stop
        self.closed = False
        self.sequences: list[int] = []

    def show_tracking(self, frame, _detections, _tracking, _detection_stats, _tracking_stats):
        self.sequences.append(frame.sequence_number)
        if self.fail:
            raise TrackingPreviewError("synthetic preview failure")
        return PreviewAction.STOP if self.stop else PreviewAction.CONTINUE

    def close(self) -> None:
        self.closed = True


def test_pipeline_preserves_detection_frame_and_stream_association() -> None:
    runner = _runner_for_batches((0,), (1,))
    detector = ScriptedDetector(
        {
            0: (pig_detection(1, 1, 4, 4),),
            1: (pig_detection(1.5, 1, 4.5, 4),),
        }
    )
    tracker = DeterministicIoUTracker(iou_threshold=0.2)
    forwarded: list[tuple[str, int, int]] = []

    summary = LiveTrackingPipeline(
        runner,  # type: ignore[arg-type]
        detector,
        tracker,
        result_callback=lambda _frame, _detections, tracking, _snapshot: forwarded.append(
            (
                tracking.source_id,
                tracking.frame_sequence,
                tracking.tracked_objects[0].track.tracker_id,
            )
        ),
    ).run()

    assert forwarded == [("camera", 0, 0), ("camera", 1, 0)]
    assert summary.tracking_statistics.tracking_requests == 2
    assert summary.tracking_statistics.tracks_emitted == 2
    assert summary.tracker_closed
    assert summary.detection_summary.camera_released


def test_pipeline_supports_zero_and_multiple_detections() -> None:
    runner = _runner_for_batches((0,), (1,))
    detector = ScriptedDetector({1: (pig_detection(1, 1, 4, 4), pig_detection(4, 1, 7, 4))})

    summary = LiveTrackingPipeline(
        runner,  # type: ignore[arg-type]
        detector,
        DeterministicIoUTracker(),
    ).run()

    statistics = summary.tracking_statistics
    assert statistics.zero_detection_updates == 1
    assert statistics.frames_without_tracks == 1
    assert statistics.frames_with_tracks == 1
    assert statistics.tracks_emitted == 2
    assert statistics.active_tracks_peak == 2


def test_temporary_tracker_failure_continues_but_fatal_failure_stops() -> None:
    temporary = FailingTracker(temporary_sequences=(0,))
    temporary_summary = LiveTrackingPipeline(
        _runner_for_batches((0,), (1,)),  # type: ignore[arg-type]
        SyntheticMovingBoxDetector(),
        temporary,
    ).run()
    assert temporary_summary.tracking_statistics.tracking_failures == 1
    assert temporary_summary.tracking_statistics.tracking_successes == 1
    assert temporary_summary.tracker_closed

    fatal = FailingTracker(fatal_sequences=(0,))
    fatal_runner = _runner_for_batches((0,))
    with pytest.raises(FatalTrackingError):
        LiveTrackingPipeline(
            fatal_runner,  # type: ignore[arg-type]
            SyntheticMovingBoxDetector(),
            fatal,
        ).run()
    assert fatal_runner.stopped
    assert not fatal.is_started


def test_detector_failure_does_not_fabricate_tracker_update() -> None:
    tracker = EmptyTracker()

    with pytest.raises(FatalInferenceError):
        LiveTrackingPipeline(
            _runner_for_batches((0,)),  # type: ignore[arg-type]
            FailingDetector(fatal_sequences=(0,)),
            tracker,
        ).run()

    assert tracker.updated_sequences == []
    assert not tracker.is_started


def test_preview_stop_and_preview_failure_are_isolated() -> None:
    stopping = TrackingPreviewDouble(stop=True)
    stopped_summary = LiveTrackingPipeline(
        _runner_for_batches((0,), (1,)),  # type: ignore[arg-type]
        EmptyDetector(),
        EmptyTracker(),
        preview=stopping,
    ).run()
    assert stopped_summary.detection_summary.shutdown_reason.value == "preview_requested"
    assert stopped_summary.tracking_statistics.tracking_successes == 1
    assert stopping.closed

    failing = TrackingPreviewDouble(fail=True)
    failure_summary = LiveTrackingPipeline(
        _runner_for_batches((0,), (1,)),  # type: ignore[arg-type]
        EmptyDetector(),
        EmptyTracker(),
        preview=failing,
    ).run()
    assert failure_summary.tracking_statistics.preview_failures == 1
    assert failure_summary.tracking_statistics.tracking_successes == 2
    assert failing.closed


def test_reconnect_resets_tracker_without_mixing_source_lifecycles() -> None:
    tracker = EmptyTracker()

    summary = LiveTrackingPipeline(
        _runner_for_batches((0,), reconnects=1),  # type: ignore[arg-type]
        EmptyDetector(),
        tracker,
    ).run()

    assert tracker.reset_count == 1
    assert summary.tracking_statistics.tracker_resets == 1
    assert summary.tracking_statistics.tracker_restarts == 1


def test_separate_pipeline_instances_isolate_stream_tracker_state() -> None:
    first = _runner_for_batches((0,))
    second = StubStreamRunner(
        scripted_reads(
            frame_packet(0, stream_id="camera-b"),
            BufferReadStatus.TIMEOUT,
            BufferReadStatus.CLOSED,
        ),
        frames_acquired=1,
    )
    second.identity = replace(second.identity, stream_id="camera-b")

    first_summary = LiveTrackingPipeline(
        first,  # type: ignore[arg-type]
        SyntheticMovingBoxDetector(),
        DeterministicIoUTracker(),
    ).run()
    second_summary = LiveTrackingPipeline(
        second,  # type: ignore[arg-type]
        SyntheticMovingBoxDetector(),
        DeterministicIoUTracker(),
    ).run()

    assert first_summary.detection_summary.source_id == "camera"
    assert second_summary.detection_summary.source_id == "camera-b"
    assert first_summary.tracking_statistics.tracks_emitted == 1
    assert second_summary.tracking_statistics.tracks_emitted == 1


def test_slow_detector_and_tracker_keep_source_buffer_bounded() -> None:
    source = SyntheticCameraSource(stream_id="camera", frame_count=100)
    buffer = BoundedFrameBuffer(BufferConfiguration(3, OverflowPolicy.DROP_OLDEST))
    runner = LiveStreamRunner(
        source,
        buffer,
        StreamConfiguration.synthetic("camera"),
        ReconnectPolicy(enabled=False),
    )

    summary = LiveTrackingPipeline(
        runner,
        SlowDetector(delay_seconds=0.005),
        DeterministicIoUTracker(),
    ).run()

    assert buffer.statistics().maximum_observed_depth <= 3
    assert summary.detection_summary.statistics.source_frames_dropped > 0
    assert summary.tracking_statistics.tracking_requests == (
        summary.tracking_statistics.tracking_successes
        + summary.tracking_statistics.tracking_failures
    )
    assert summary.tracker_closed


def test_keyboard_interrupt_closes_tracker_and_camera() -> None:
    runner = StubStreamRunner(scripted_reads(KeyboardInterrupt()), frames_acquired=0)
    tracker = EmptyTracker()

    summary = LiveTrackingPipeline(
        runner,  # type: ignore[arg-type]
        EmptyDetector(),
        tracker,
    ).run()

    assert summary.detection_summary.shutdown_reason.value == "keyboard_interrupt"
    assert summary.tracker_closed
    assert summary.detection_summary.camera_released
