import json
import subprocess
import sys
from pathlib import Path

import pytest

from hogflow.adapters.camera_stream_cli import build_parser, main
from hogflow.streaming.buffering import BoundedFrameBuffer

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_cli_help_is_headless_and_source_explicit() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "hogflow.adapters.camera_stream_cli", "--help"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    for option in (
        "--source-type",
        "--rtsp-url",
        "--device-index",
        "--file",
        "--buffer-size",
        "--overflow-policy",
        "--reconnect",
        "--no-display",
    ):
        assert option in result.stdout


def test_parser_supports_all_explicit_source_types() -> None:
    help_text = build_parser().format_help()

    assert "{usb,rtsp,file,synthetic}" in help_text


def test_synthetic_cli_reports_only_sanitized_aggregates_and_writes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    status = main(
        [
            "--source-type",
            "synthetic",
            "--stream-id",
            "diagnostic",
            "--duration",
            "1",
            "--max-frames",
            "6",
            "--buffer-size",
            "2",
            "--no-display",
        ]
    )

    lines = capsys.readouterr().out.splitlines()
    payload = json.loads(lines[-1])
    assert status == 0
    assert payload["source_id"] == "synthetic-camera:diagnostic"
    assert payload["frames_acquired"] == 6
    assert payload["frames_dropped"] >= 0
    assert list(tmp_path.iterdir()) == []


def test_rtsp_cli_requires_runtime_locator_without_echoing_value() -> None:
    with pytest.raises(SystemExit):
        main(["--source-type", "rtsp", "--duration", "0.1"])


def test_keyboard_interrupt_stops_diagnostic_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        BoundedFrameBuffer,
        "get",
        lambda _self, timeout_seconds=None: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    assert main(["--source-type", "synthetic", "--duration", "1"]) == 0
    assert '"final": true' in capsys.readouterr().out
