from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from threading import Event

from hogflow.application.autonomous_demo import (
    AutonomousDemoController,
    AutonomousDemoState,
)
from hogflow.calibration import (
    AutonomousCalibrationResult,
    AutonomousDemoProgress,
    AutonomousDemoResult,
    CalibrationConfidence,
    CalibrationStatus,
)
from hogflow.camera import LatestPreviewFrameChannel, PreviewConfiguration
from hogflow.detection import PigDetectorConfiguration


def _inconclusive_result() -> AutonomousDemoResult:
    calibration = AutonomousCalibrationResult(
        status=CalibrationStatus.INCONCLUSIVE,
        confidence=CalibrationConfidence.INCONCLUSIVE,
        dominant_direction=None,
        direction_purity=0.0,
        eligible_track_count=0,
        selected_line=None,
        selected_positive_direction=None,
        selected_score=0.0,
        corridor=None,
        candidate_metrics=(),
        line_band_counts=(),
        detector_perturbation_counts=(),
        counting_configuration=None,
        limitations=("autonomous_consistency_only",),
        algorithm_version="phase_10_3c_a_v2",
    )
    return AutonomousDemoResult(
        demo_id="operator_autonomous_demo",
        calibration=calibration,
        primary_count=None,
        primary_count_direction=None,
        calibration_crossing_events=0,
        counting_crossing_events=0,
        pass_two_first_frame_sequence=None,
        calibration_frames=0,
        counting_frames=0,
        calibration_fps=0.0,
        counting_fps=0.0,
        average_detector_latency_ms=0.0,
        hmi_state="AUTOCALIBRATION INCONCLUSIVE",
        failures=(),
        limitations=("human_ground_truth_not_measured",),
    )


def _compatible_detector(tmp_path: Path) -> tuple[PigDetectorConfiguration, str]:
    model = tmp_path / "demo.pt"
    model.write_bytes(b"synthetic-model")
    fingerprint = hashlib.sha256(model.read_bytes()).hexdigest()
    return (
        PigDetectorConfiguration.local_model(
            model,
            target_class_name="pig",
            target_class_ids=(0,),
            confidence_threshold=0.25,
            iou_threshold=0.5,
            inference_image_size=640,
            maximum_detections=300,
            half_precision=False,
        ),
        fingerprint,
    )


def test_autonomous_demo_bridge_is_async_and_path_free(tmp_path: Path) -> None:
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"local-test-placeholder")
    finished = Event()

    def run(video_path: Path, progress) -> AutonomousDemoResult:
        assert video_path == video
        progress("calibrating", None)
        finished.set()
        return _inconclusive_result()

    detector, fingerprint = _compatible_detector(tmp_path)
    controller = AutonomousDemoController(
        run,
        detector_configuration=detector,
        expected_artifact_fingerprint=fingerprint,
    )
    starting = controller.start(video)

    assert starting.state is AutonomousDemoState.CALIBRATING
    assert starting.worker_alive
    assert finished.wait(1.0)
    final = controller.close()
    assert final.state is AutonomousDemoState.INCONCLUSIVE
    assert not final.worker_alive
    assert str(video) not in repr(final)


def test_live_count_progress_is_retained_as_latest_bounded_snapshot(tmp_path: Path) -> None:
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"local-test-placeholder")
    channel = LatestPreviewFrameChannel(PreviewConfiguration())
    finished = Event()
    observed_counts: list[int] = []
    observed_snapshots: list[int | None] = []

    def run(_video_path: Path, progress) -> AutonomousDemoResult:
        for count in range(4):
            progress(
                "counting",
                None,
                AutonomousDemoProgress(
                    stage="counting",
                    frame_sequence=count,
                    current_count=count,
                    frames_processed=count + 1,
                ),
            )
            observed_counts.append(count)
            observed_snapshots.append(controller.snapshot().live_count)
        finished.set()
        return _inconclusive_result()

    detector, fingerprint = _compatible_detector(tmp_path)
    controller = AutonomousDemoController(
        run,
        preview_channel=channel,
        detector_configuration=detector,
        expected_artifact_fingerprint=fingerprint,
    )
    controller.start(video)
    assert finished.wait(1.0)
    snapshot = controller.snapshot()
    controller.close()

    assert observed_counts == [0, 1, 2, 3]
    assert observed_snapshots == [0, 1, 2, 3]
    assert snapshot.frames_processed == 4
    assert snapshot.crossing_events == 0
    assert channel.snapshot().frames_published == 0


def test_cancel_during_count_returns_cancelled_without_lingering_worker(tmp_path: Path) -> None:
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"local-test-placeholder")
    started = Event()

    def run(_video_path: Path, progress, should_stop) -> AutonomousDemoResult:
        started.set()
        while not should_stop():
            progress("counting", None)
        return _inconclusive_result()

    detector, fingerprint = _compatible_detector(tmp_path)
    controller = AutonomousDemoController(
        run,
        detector_configuration=detector,
        expected_artifact_fingerprint=fingerprint,
        worker_join_timeout_seconds=1.0,
    )
    controller.start(video)
    assert started.wait(1.0)
    controller.cancel()
    final = controller.close()

    assert final.state is AutonomousDemoState.CANCELLED
    assert not final.worker_alive


def test_cancel_during_calibration_is_explicit_state(tmp_path: Path) -> None:
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"local-test-placeholder")
    started = Event()

    def run(_video_path: Path, progress, should_stop) -> AutonomousDemoResult:
        started.set()
        while not should_stop():
            progress("calibrating", None)
        return _inconclusive_result()

    detector, fingerprint = _compatible_detector(tmp_path)
    controller = AutonomousDemoController(
        run,
        detector_configuration=detector,
        expected_artifact_fingerprint=fingerprint,
        worker_join_timeout_seconds=1.0,
    )
    controller.start(video)
    assert started.wait(1.0)
    controller.cancel()
    final = controller.close()

    assert final.state is AutonomousDemoState.CANCELLED
    assert final.message.startswith("Auto Demo cancelled")


def test_failed_result_keeps_failure_snapshot_sanitized(tmp_path: Path) -> None:
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"local-test-placeholder")
    detector, fingerprint = _compatible_detector(tmp_path)
    started = Event()
    release = Event()
    failed_calibration = replace(
        _inconclusive_result().calibration, status=CalibrationStatus.FAILED
    )
    result = replace(
        _inconclusive_result(),
        calibration=failed_calibration,
        hmi_state="AUTOCALIBRATION FAILED",
        failures=(str(video),),
    )

    def run(*_args) -> AutonomousDemoResult:
        started.set()
        release.wait(1.0)
        return result

    controller = AutonomousDemoController(
        run,
        detector_configuration=detector,
        expected_artifact_fingerprint=fingerprint,
    )
    controller.start(video)
    assert started.wait(1.0)
    assert controller.snapshot().worker_alive
    release.set()
    final = controller.close()

    assert final.state is AutonomousDemoState.FAILED
    assert final.failures == ("bounded_runtime_failure",)
    assert str(video) not in repr(final)


def test_autonomous_demo_requires_the_frozen_detector_configuration(tmp_path: Path) -> None:
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"local-test-placeholder")
    model = tmp_path / "demo.pt"
    model.write_bytes(b"synthetic-model")
    fingerprint = hashlib.sha256(model.read_bytes()).hexdigest()

    correct = PigDetectorConfiguration.local_model(
        model,
        target_class_name="pig",
        target_class_ids=(0,),
        confidence_threshold=0.25,
        iou_threshold=0.5,
        inference_image_size=640,
        maximum_detections=300,
        half_precision=False,
    )
    assert AutonomousDemoController(
        lambda *_args: _inconclusive_result(),
        detector_configuration=correct,
        expected_artifact_fingerprint=fingerprint,
    ).detector_ready
    assert not AutonomousDemoController(
        lambda *_args: _inconclusive_result(),
        detector_configuration=PigDetectorConfiguration.empty(),
    ).detector_ready
    wrong_confidence = PigDetectorConfiguration.local_model(
        model,
        target_class_name="pig",
        target_class_ids=(0,),
        confidence_threshold=0.4,
        iou_threshold=0.5,
        inference_image_size=640,
        maximum_detections=300,
        half_precision=False,
    )
    assert not AutonomousDemoController(
        lambda *_args: _inconclusive_result(),
        detector_configuration=wrong_confidence,
        expected_artifact_fingerprint=fingerprint,
    ).detector_ready
