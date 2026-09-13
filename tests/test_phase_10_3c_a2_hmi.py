from __future__ import annotations

from pathlib import Path

from _phase9_helpers import operator_application

from hogflow.application import (
    AutonomousDemoSnapshot,
    AutonomousDemoState,
    VideoSourceRequest,
)
from hogflow.bootstrap import build_operator_runtime
from hogflow.calibration import (
    AutonomousCalibrationResult,
    CalibrationConfidence,
    CalibrationStatus,
    CountingGeometryConfiguration,
    DirectionVector,
)
from hogflow.counting import LiveCrossingDirection, NormalizedLine, NormalizedPoint
from hogflow.presentation import OperatorAction, screen_from_snapshot

_SHA = "0" * 64


def _calibration(confidence: CalibrationConfidence) -> AutonomousCalibrationResult:
    line = NormalizedLine(NormalizedPoint(0.1, 0.5), NormalizedPoint(0.9, 0.5))
    geometry = CountingGeometryConfiguration(
        detector_artifact_fingerprint=_SHA,
        detector_configuration_fingerprint=_SHA,
        tracker_configuration_fingerprint=_SHA,
        line=line,
        positive_direction=LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
        crossing_epsilon=0.005,
        absent_track_retention_updates=30,
        algorithm_version="phase_10_3c_a_v2",
        settings_fingerprint=_SHA,
    )
    return AutonomousCalibrationResult(
        status=CalibrationStatus.READY,
        confidence=confidence,
        dominant_direction=DirectionVector(0.0, 1.0),
        direction_purity=1.0,
        eligible_track_count=3,
        selected_line=line,
        selected_positive_direction=LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
        selected_score=0.8,
        corridor=None,
        candidate_metrics=(),
        line_band_counts=(3,),
        detector_perturbation_counts=(),
        counting_configuration=geometry,
        limitations=("autonomous_consistency_only",),
        algorithm_version="phase_10_3c_a_v2",
    )


def test_live_count_and_locked_line_are_projected_after_counting() -> None:
    application, _coordinator = operator_application()
    screen = screen_from_snapshot(
        application.snapshot(),
        autonomous_demo=AutonomousDemoSnapshot(
            state=AutonomousDemoState.COUNTING,
            calibration=_calibration(CalibrationConfidence.HIGH),
            live_count=2,
            observed_count_min=2,
            observed_count_max=3,
        ),
    )

    assert screen.autonomous_demo.live_count == 2
    assert screen.autonomous_demo.counting_line == "LOCKED"
    assert screen.autonomous_demo.line_coordinates == (0.1, 0.5, 0.9, 0.5)


def test_low_consistency_remains_visible_after_completion() -> None:
    application, _coordinator = operator_application()
    screen = screen_from_snapshot(
        application.snapshot(),
        autonomous_demo=AutonomousDemoSnapshot(
            state=AutonomousDemoState.COMPLETE,
            calibration=_calibration(CalibrationConfidence.LOW),
            live_count=6,
            observed_count_min=3,
            observed_count_max=6,
        ),
    )

    assert screen.autonomous_demo.state == "COMPLETE"
    assert screen.autonomous_demo.consistency == "LOW"
    assert screen.autonomous_demo.live_count == 6


def test_low_consistency_uses_required_manager_copy() -> None:
    application, _coordinator = operator_application()
    screen = screen_from_snapshot(
        application.snapshot(),
        autonomous_demo=AutonomousDemoSnapshot(
            state=AutonomousDemoState.LOW_CONFIDENCE,
            calibration=_calibration(CalibrationConfidence.LOW),
            live_count=6,
        ),
    )

    assert screen.autonomous_demo.state == "LOW CONSISTENCY"


def test_inconclusive_calibration_keeps_line_unlocked_and_count_hidden() -> None:
    application, _coordinator = operator_application()
    screen = screen_from_snapshot(
        application.snapshot(),
        autonomous_demo=AutonomousDemoSnapshot(
            state=AutonomousDemoState.INCONCLUSIVE,
            message="Autocalibration is inconclusive.",
        ),
    )

    assert screen.autonomous_demo.counting_line == "UNLOCKED"
    assert screen.autonomous_demo.line_coordinates is None
    assert screen.autonomous_demo.live_count is None


def test_running_autonomous_demo_blocks_normal_pipeline_actions(tmp_path: Path) -> None:
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"synthetic")
    runtime = build_operator_runtime()
    runtime.application.configure_video_source(VideoSourceRequest.video_file(video))

    screen = screen_from_snapshot(
        runtime.application.snapshot(),
        pipeline=runtime.application.pipeline_snapshot(),
        autonomous_demo=AutonomousDemoSnapshot(
            state=AutonomousDemoState.COUNTING,
            worker_alive=True,
            live_count=2,
        ),
        autonomous_demo_available=True,
    )

    assert not screen.actions.is_enabled(OperatorAction.CONFIGURE_SOURCE)
    assert not screen.actions.is_enabled(OperatorAction.START_PIPELINE)
    assert not screen.actions.is_enabled(OperatorAction.RESTART_VIDEO)
    assert not screen.actions.is_enabled(OperatorAction.START_AUTONOMOUS_DEMO)
    assert screen.actions.is_enabled(OperatorAction.CANCEL_AUTONOMOUS_DEMO)
