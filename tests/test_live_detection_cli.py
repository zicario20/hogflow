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
        "--tracker",
        "--lost-track-buffer",
        "--tracker-frame-rate",
        "--show-track-ids",
        "--enable-crossing",
        "--crossing-line-start",
        "--crossing-line-end",
        "--crossing-anchor",
        "--enable-counting",
        "--positive-direction",
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


def test_synthetic_tracking_cli_emits_structured_temporary_id_summary(capsys) -> None:
    result = main(
        [
            "--source-type",
            "synthetic",
            "--synthetic-frames",
            "8",
            "--detector",
            "synthetic-moving",
            "--tracker",
            "deterministic-iou",
            "--statistics-interval",
            "100",
        ]
    )

    payload = json.loads([line for line in capsys.readouterr().out.splitlines() if line][-1])
    assert result == 0
    assert payload["tracking_enabled"] is True
    assert payload["tracker_identity"] == "deterministic-iou-tracker"
    assert payload["tracks_emitted"] > 0
    assert payload["tracker_closed"] is True
    assert "count" not in payload


def test_synthetic_crossing_cli_emits_event_diagnostics_without_animal_total(capsys) -> None:
    result = main(
        [
            "--source-type",
            "synthetic",
            "--synthetic-frames",
            "4",
            "--tracker",
            "empty",
            "--enable-crossing",
            "--crossing-line-start",
            "0.1,0.5",
            "--crossing-line-end",
            "0.9,0.5",
            "--statistics-interval",
            "100",
        ]
    )

    payload = json.loads([line for line in capsys.readouterr().out.splitlines() if line][-1])
    assert result == 0
    assert payload["crossing_enabled"] is True
    assert payload["crossing_events_emitted"] == 0
    assert payload["crossing_closed"] is True
    assert "total_pigs" not in payload
    assert "animal_count" not in payload


def test_synthetic_counting_cli_emits_lifecycle_total_without_session_state(capsys) -> None:
    result = main(
        [
            "--source-type",
            "synthetic",
            "--synthetic-frames",
            "4",
            "--tracker",
            "empty",
            "--enable-crossing",
            "--crossing-line-start",
            "0.1,0.5",
            "--crossing-line-end",
            "0.9,0.5",
            "--enable-counting",
            "--positive-direction",
            "negative_to_positive",
            "--statistics-interval",
            "100",
        ]
    )

    payload = json.loads([line for line in capsys.readouterr().out.splitlines() if line][-1])
    assert result == 0
    assert payload["counting_enabled"] is True
    assert payload["lifecycle_directional_count"] == 0
    assert payload["counting_closed"] is True
    assert "session_id" not in payload
    assert "storage" not in payload


@pytest.mark.parametrize(
    "arguments",
    (
        ["--source-type", "synthetic", "--enable-counting"],
        [
            "--source-type",
            "synthetic",
            "--tracker",
            "empty",
            "--enable-crossing",
            "--crossing-line-start",
            "0.1,0.5",
            "--crossing-line-end",
            "0.9,0.5",
            "--enable-counting",
        ],
        [
            "--source-type",
            "synthetic",
            "--positive-direction",
            "negative_to_positive",
        ],
        [
            "--source-type",
            "synthetic",
            "--tracker",
            "empty",
            "--enable-crossing",
            "--crossing-line-start",
            "0.1,0.5",
            "--crossing-line-end",
            "0.9,0.5",
            "--enable-counting",
            "--positive-direction",
            "negative_to_positive",
            "--maximum-counted-identities",
            "0",
        ],
    ),
)
def test_cli_rejects_invalid_counting_configuration_before_runtime(
    arguments: list[str],
) -> None:
    with pytest.raises(SystemExit) as captured:
        main(arguments)

    assert captured.value.code == 2


@pytest.mark.parametrize(
    "arguments",
    (
        ["--source-type", "synthetic", "--enable-crossing"],
        [
            "--source-type",
            "synthetic",
            "--tracker",
            "empty",
            "--enable-crossing",
            "--crossing-line-start",
            "0.1,0.5",
        ],
        [
            "--source-type",
            "synthetic",
            "--tracker",
            "empty",
            "--crossing-line-start",
            "0.1,0.5",
        ],
        [
            "--source-type",
            "synthetic",
            "--tracker",
            "empty",
            "--enable-crossing",
            "--crossing-line-start",
            "2,0.5",
            "--crossing-line-end",
            "0.9,0.5",
        ],
    ),
)
def test_cli_rejects_incomplete_or_invalid_crossing_configuration(
    arguments: list[str],
) -> None:
    with pytest.raises(SystemExit) as captured:
        main(arguments)

    assert captured.value.code == 2


@pytest.mark.parametrize(
    "arguments",
    (
        ["--source-type", "synthetic", "--lost-track-buffer", "-1", "--tracker", "bytetrack"],
        ["--source-type", "synthetic", "--tracker-frame-rate", "0", "--tracker", "bytetrack"],
        [
            "--source-type",
            "synthetic",
            "--minimum-consecutive-frames",
            "0",
            "--tracker",
            "bytetrack",
        ],
    ),
)
def test_cli_rejects_invalid_tracker_configuration(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as captured:
        main(arguments)

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
