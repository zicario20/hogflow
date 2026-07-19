import json

import pytest

from hogflow.video.live_detection_cli import build_parser, main


def test_live_detection_cli_help_lists_source_detector_and_scheduling_options() -> None:
    help_text = build_parser().format_help()

    for option in (
        "--source-type",
        "--device-index",
        "--rtsp-url",
        "--detector",
        "--model-path",
        "--inference-every",
        "--target-inference-fps",
        "--maximum-frame-age-ms",
        "--preview",
    ):
        assert option in help_text


def test_synthetic_empty_detector_cli_emits_sanitized_final_json(capsys) -> None:
    result = main(
        [
            "--source-type",
            "synthetic",
            "--synthetic-frames",
            "8",
            "--statistics-interval",
            "100",
        ]
    )

    lines = [line for line in capsys.readouterr().out.splitlines() if line]
    payload = json.loads(lines[-1])
    assert result == 0
    assert payload["final"] is True
    assert payload["source"] == "synthetic"
    assert payload["detector_identity"] == "empty-detector"
    assert payload["pig_model_provenance_complete"] is False
    assert payload["total_detections"] == 0
    assert payload["camera_released"] is True
    assert payload["detector_closed"] is True
    assert "\\" not in payload["source_identity"]
    assert "/" not in payload["source_identity"]


def test_yolo_cli_requires_explicit_local_model_path() -> None:
    with pytest.raises(SystemExit) as captured:
        main(["--source-type", "synthetic", "--detector", "yolo"])

    assert captured.value.code == 2


@pytest.mark.parametrize(
    "arguments",
    (
        ["--source-type", "synthetic", "--inference-every", "0"],
        ["--source-type", "synthetic", "--confidence", "0"],
        ["--source-type", "synthetic", "--target-inference-fps", "nan"],
    ),
)
def test_cli_rejects_invalid_runtime_configuration(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as captured:
        main(arguments)

    assert captured.value.code == 2
