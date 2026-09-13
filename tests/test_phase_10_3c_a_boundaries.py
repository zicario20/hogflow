from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_formal_phase_10_3c_human_boundary_remains_unchanged() -> None:
    report = (ROOT / "docs/phase_10/phase_10_3c_independent_validation.md").read_text(
        encoding="utf-8"
    )

    assert "Status: **BLOCKED — HUMAN INPUT REQUIRED**" in report
    assert "A/B MANUAL CROSSING GROUND TRUTH REQUIRED" in report
    assert "No Video C is authorized." in report
    assert "DEMO MODEL — NOT PRODUCTION VALIDATED." in report


def test_autonomous_report_is_path_free_and_truthful() -> None:
    report = (ROOT / "docs/phase_10/phase_10_3c_a_autonomous_demo.md").read_text(encoding="utf-8")

    assert "AUTONOMOUS AI VALIDATION — HUMAN GROUND TRUTH NOT MEASURED" in report
    assert "accuracy" not in report.casefold()
    assert "production validated" in report.casefold()
    assert "\\" not in report
    assert "data/raw/" not in report


def test_autonomous_local_output_root_is_ignored() -> None:
    output = subprocess.run(
        ["git", "check-ignore", "data/evaluation/phase10_3c_a/result.json"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert output.returncode == 0


def test_no_real_media_or_weights_are_tracked() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "*.mp4", "*.pt", "*.onnx", "*.engine"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert tracked.stdout.strip() == ""
