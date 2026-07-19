from __future__ import annotations

from time import monotonic

import pytest
from _phase5_2_helpers import StubStreamRunner, frame_packet, scripted_reads

from hogflow.detection import (
    EmptyDetector,
    FailingDetector,
    LiveInferenceConfiguration,
    PreviewAction,
    ScriptedDetector,
    SlowDetector,
)
from hogflow.detection.errors import DetectionPreviewError, FatalInferenceError
from hogflow.models import BoundingBox, Detection
from hogflow.pipeline.live_detection_pipeline import LiveDetectionPipeline
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


class PreviewDouble:
    def __init__(self, *, fail: bool = False, stop: bool = False) -> None:
        self.fail = fail
        self.stop = stop
        self.closed = False
        self.sequences: list[int] = []

    def show(self, frame, _detections, _statistics):
        self.sequences.append(frame.sequence_number)
        if self.fail:
            raise DetectionPreviewError("synthetic preview failure")
        return PreviewAction.STOP if self.stop else PreviewAction.CONTINUE

    def close(self) -> None:
        self.closed = True


def _runner_for_batches(*batches: tuple[int, ...], drops: int = 0) -> StubStreamRunner:
    reads: list[object] = []
    total = 0
    for batch in batches:
        reads.extend(frame_packet(sequence) for sequence in batch)
        reads.append(BufferReadStatus.TIMEOUT)
        total += len(batch)
    reads.append(BufferReadStatus.CLOSED)
    return StubStreamRunner(
        scripted_reads(*reads),
        frames_acquired=total + drops,
        frames_dropped=drops,
    )


def test_pipeline_preserves_frame_identity_and_multiple_boxes() -> None:
    boxes = (
        Detection(BoundingBox(0, 0, 2, 2), 0.8, 0, "pig"),
        Detection(BoundingBox(3, 1, 7, 5), 0.9, 0, "pig"),
    )
    detector = ScriptedDetector({3: boxes})
    runner = _runner_for_batches((3,))
    forwarded: list[tuple[int, int]] = []

    summary = LiveDetectionPipeline(
        runner,  # type: ignore[arg-type]
        detector,
        result_callback=lambda frame, result, _stats: forwarded.append(
            (frame.sequence_number, result.frame_sequence)
        ),
    ).run()

    assert forwarded == [(3, 3)]
    assert summary.statistics.frames_inferred == 1
    assert summary.statistics.total_detections == 2
    assert summary.detector.model_id == "scripted-detector"
    assert summary.camera_released
    assert summary.detector_closed


def test_pipeline_drains_to_latest_frame_and_separates_camera_drops() -> None:
    runner = _runner_for_batches((0, 1, 2), drops=4)
    detector = EmptyDetector()

    summary = LiveDetectionPipeline(runner, detector).run()  # type: ignore[arg-type]

    assert detector.inferred_sequences == [2]
    assert summary.statistics.frames_acquired == 7
    assert summary.statistics.frames_submitted == 3
    assert summary.statistics.frames_skipped == 2
    assert summary.statistics.source_frames_dropped == 4


def test_pipeline_applies_every_n_and_maximum_frame_age_without_blocking_acquisition() -> None:
    now = monotonic()
    old = frame_packet(2, monotonic_seconds=now - 5)
    reads = scripted_reads(
        frame_packet(1),
        BufferReadStatus.TIMEOUT,
        old,
        BufferReadStatus.TIMEOUT,
        frame_packet(4),
        BufferReadStatus.TIMEOUT,
        BufferReadStatus.CLOSED,
    )
    runner = StubStreamRunner(reads, frames_acquired=3)
    detector = EmptyDetector()

    summary = LiveDetectionPipeline(
        runner,  # type: ignore[arg-type]
        detector,
        LiveInferenceConfiguration(inference_every_n_frames=2, maximum_frame_age_ms=100),
    ).run()

    assert detector.inferred_sequences == [4]
    assert summary.statistics.frames_skipped == 2
    assert summary.statistics.frames_inferred == 1


def test_target_inference_fps_skips_without_sleeping() -> None:
    runner = _runner_for_batches((0,), (1,))
    detector = EmptyDetector(monotonic_clock=lambda: 100.0)

    summary = LiveDetectionPipeline(
        runner,  # type: ignore[arg-type]
        detector,
        LiveInferenceConfiguration(target_inference_fps=10),
        monotonic_clock=lambda: 100.0,
    ).run()

    assert detector.inferred_sequences == [0]
    assert summary.statistics.frames_inferred == 1
    assert summary.statistics.frames_skipped == 1


def test_temporary_failure_continues_and_fatal_failure_releases_resources() -> None:
    temporary = FailingDetector(temporary_sequences=(0,))
    temporary_runner = _runner_for_batches((0,), (1,))

    temporary_summary = LiveDetectionPipeline(
        temporary_runner,  # type: ignore[arg-type]
        temporary,
    ).run()

    assert temporary_summary.statistics.inference_failures == 1
    assert temporary_summary.statistics.frames_inferred == 1

    fatal = FailingDetector(fatal_sequences=(0,))
    fatal_runner = _runner_for_batches((0,))
    with pytest.raises(FatalInferenceError):
        LiveDetectionPipeline(fatal_runner, fatal).run()  # type: ignore[arg-type]
    assert fatal_runner.stopped
    assert fatal_runner.joined
    assert not fatal.is_loaded


def test_keyboard_interrupt_and_preview_failure_use_cooperative_cleanup() -> None:
    interrupted_runner = StubStreamRunner(
        scripted_reads(KeyboardInterrupt()),
        frames_acquired=0,
    )
    detector = EmptyDetector()

    summary = LiveDetectionPipeline(
        interrupted_runner,  # type: ignore[arg-type]
        detector,
    ).run()

    assert summary.shutdown_reason.value == "keyboard_interrupt"
    assert interrupted_runner.stopped
    assert summary.camera_released

    preview = PreviewDouble(fail=True)
    preview_runner = _runner_for_batches((0,), (1,))
    preview_summary = LiveDetectionPipeline(
        preview_runner,  # type: ignore[arg-type]
        EmptyDetector(),
        preview=preview,
    ).run()

    assert preview_summary.statistics.preview_failures == 1
    assert preview_summary.statistics.frames_inferred == 2
    assert preview.closed


def test_preview_can_request_clean_stop() -> None:
    preview = PreviewDouble(stop=True)
    runner = _runner_for_batches((0,), (1,))

    summary = LiveDetectionPipeline(
        runner,  # type: ignore[arg-type]
        EmptyDetector(),
        preview=preview,
    ).run()

    assert summary.shutdown_reason.value == "preview_requested"
    assert summary.statistics.frames_inferred == 1


def test_slow_detector_keeps_the_real_source_buffer_bounded() -> None:
    source = SyntheticCameraSource(stream_id="camera", frame_count=100)
    configuration = StreamConfiguration.synthetic("camera")
    buffer = BoundedFrameBuffer(BufferConfiguration(3, OverflowPolicy.DROP_OLDEST))
    runner = LiveStreamRunner(
        source,
        buffer,
        configuration,
        ReconnectPolicy(enabled=False),
    )

    summary = LiveDetectionPipeline(
        runner,
        SlowDetector(delay_seconds=0.01),
    ).run()

    assert runner.buffer.statistics().maximum_observed_depth <= 3
    assert summary.statistics.source_frames_dropped > 0
    assert summary.statistics.frames_inferred >= 1
    assert summary.statistics.frames_submitted == (
        summary.statistics.frames_inferred
        + summary.statistics.frames_skipped
        + summary.statistics.inference_failures
    )
    assert summary.camera_released


def test_maximum_frames_stops_at_the_detection_submission_boundary() -> None:
    runner = _runner_for_batches((0, 1, 2, 3))

    summary = LiveDetectionPipeline(
        runner,  # type: ignore[arg-type]
        EmptyDetector(),
    ).run(maximum_frames=2)

    assert summary.statistics.frames_submitted == 2
    assert summary.statistics.frames_skipped == 1
    assert summary.statistics.frames_inferred == 1
    assert summary.shutdown_reason.value == "maximum_frames"


def test_stub_helper_uses_explicit_buffer_outcomes() -> None:
    runner = _runner_for_batches((0,))
    runner.start()

    assert runner.buffer.get(0).status is BufferReadStatus.FRAME
    assert runner.buffer.get(0).status is BufferReadStatus.TIMEOUT
    assert runner.buffer.get(0).status is BufferReadStatus.CLOSED
