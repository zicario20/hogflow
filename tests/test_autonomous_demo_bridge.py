from __future__ import annotations

from pathlib import Path
from threading import Event

from hogflow.application.autonomous_demo import (
    AutonomousDemoController,
    AutonomousDemoState,
)
from hogflow.calibration import (
    AutonomousCalibrationResult,
    AutonomousDemoResult,
    CalibrationConfidence,
    CalibrationStatus,
)


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


def test_autonomous_demo_bridge_is_async_and_path_free(tmp_path: Path) -> None:
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"local-test-placeholder")
    finished = Event()

    def run(video_path: Path, progress) -> AutonomousDemoResult:
        assert video_path == video
        progress("calibrating", None)
        finished.set()
        return _inconclusive_result()

    controller = AutonomousDemoController(run)
    starting = controller.start(video)

    assert starting.state is AutonomousDemoState.CALIBRATING
    assert starting.worker_alive
    assert finished.wait(1.0)
    final = controller.close()
    assert final.state is AutonomousDemoState.INCONCLUSIVE
    assert not final.worker_alive
    assert str(video) not in repr(final)
