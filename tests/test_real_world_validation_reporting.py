from __future__ import annotations

import json
from pathlib import Path

from _phase10_3_helpers import (
    NOW,
    FakeGitPolicy,
    FakeMetadataInspector,
    create_authorized_media,
)

from hogflow.validation import (
    LocalValidationWorkspace,
    RealWorldValidationWorkflow,
    validation_report_json,
    validation_report_markdown,
    write_validation_report,
)


def _blocked_report(tmp_path: Path):
    create_authorized_media(tmp_path)
    workspace = LocalValidationWorkspace(
        tmp_path,
        FakeMetadataInspector(),
        git_policy=FakeGitPolicy(),  # type: ignore[arg-type]
    )
    return RealWorldValidationWorkflow(clock=lambda: NOW).run(
        workspace=workspace,
        inspected_videos=workspace.inspect_authorized_videos(),
        model_availability=workspace.locate_model(),
    )


def test_json_report_is_deterministic_and_has_explicit_evidence_states(tmp_path: Path) -> None:
    report = _blocked_report(tmp_path)
    first = validation_report_json(report)
    second = validation_report_json(report)
    payload = json.loads(first)

    assert first == second
    assert payload["report_fingerprint"] == report.report_fingerprint
    assert payload["results"][0]["performance"]["frames_processed"]["state"] == "unknown"
    assert payload["results"][0]["metadata"]["frame_count"]["state"] == "measured"


def test_reports_expose_no_local_path_filename_media_or_framework_object(tmp_path: Path) -> None:
    report = _blocked_report(tmp_path)
    content = validation_report_json(report) + validation_report_markdown(report)
    forbidden = (
        str(tmp_path),
        "WhatsApp Video",
        "data/raw",
        "cv2",
        "numpy",
        "ultralytics",
        "torch",
        "private-pig-model",
    )
    assert not any(item.casefold() in content.casefold() for item in forbidden)


def test_markdown_preserves_three_separate_video_sections(tmp_path: Path) -> None:
    content = validation_report_markdown(_blocked_report(tmp_path))
    assert content.count("## video_") == 3
    assert "REAL DETECTOR VALIDATION COULD NOT BE COMPLETED" in content
    assert "NOT VALID FOR COUNTING ACCURACY" in content


def test_report_writer_writes_json_and_markdown_atomically(tmp_path: Path) -> None:
    report = _blocked_report(tmp_path / "workspace")
    output = tmp_path / "output"
    json_path = output / "report.json"
    markdown_path = output / "report.md"
    write_validation_report(report, json_path=json_path, markdown_path=markdown_path)

    assert json.loads(json_path.read_text(encoding="utf-8"))["report_fingerprint"]
    assert markdown_path.read_text(encoding="utf-8").startswith("# HogFlow")
    assert not tuple(output.glob("*.tmp"))
