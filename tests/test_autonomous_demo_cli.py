from __future__ import annotations

import json

import pytest

from hogflow import __main__ as cli
from hogflow.calibration import (
    AutonomousCalibrationResult,
    AutonomousDemoResult,
    CalibrationConfidence,
    CalibrationStatus,
)
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
        limitations=(
            "autonomous_consistency_only",
            "human_ground_truth_not_measured",
        ),
    )
    return AutonomousDemoResult(
        demo_id="autonomous_demo_video_1",
        calibration=calibration,
        primary_count=None,
        primary_count_direction=None,
        calibration_crossing_events=0,
        counting_crossing_events=0,
        pass_two_first_frame_sequence=None,
        calibration_frames=12,
        counting_frames=0,
        calibration_fps=1.0,
        counting_fps=0.0,
        average_detector_latency_ms=1.0,
        hmi_state="AUTOCALIBRATION INCONCLUSIVE",
        failures=(),
        limitations=calibration.limitations,
    )


def test_parser_exposes_autonomous_demo_help() -> None:
    parser = cli.build_parser()

    arguments = parser.parse_args(["autonomous-demo", "--video", "demo.mp4"])

    assert arguments.command == "autonomous-demo"
    assert arguments.video == "demo.mp4"


def test_autonomous_demo_rejects_empty_detector() -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(["autonomous-demo", "--video", "demo.mp4"])

    assert error.value.code == 2


def test_inconclusive_output_is_sanitized_and_nonzero(monkeypatch, capsys, tmp_path) -> None:
    model_path = tmp_path / "model.pt"
    model_path.write_bytes(b"synthetic")
    monkeypatch.setattr(
        cli,
        "_detector_configuration",
        lambda _arguments: PigDetectorConfiguration.local_model(
            model_path,
            target_class_name="pig",
            target_class_ids=(0,),
            confidence_threshold=0.25,
            iou_threshold=0.5,
            inference_image_size=640,
            maximum_detections=300,
        ),
    )
    monkeypatch.setattr(cli, "run_autonomous_demo", lambda *args, **kwargs: _inconclusive_result())

    result = cli.main(
        [
            "autonomous-demo",
            "--video",
            r"C:\private\pig video.mp4",
            "--detector",
            "ultralytics",
            "--model-path",
            str(model_path),
            "--target-class-id",
            "0",
            "--confidence-threshold",
            "0.25",
        ]
    )

    assert result != 0
    output = capsys.readouterr().out
    payload = json.loads(output)
    assert payload["status"] == "inconclusive"
    assert "private" not in output
    assert "pig video" not in output
