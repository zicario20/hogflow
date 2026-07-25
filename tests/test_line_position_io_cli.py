from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from _phase6_helpers import clean_pass_replay, three_candidate_plan

from hogflow.evaluation import VirtualLinePositionEvaluator
from hogflow.evaluation.line_errors import (
    LineEvaluationOutputError,
    LineEvaluationSchemaError,
)
from hogflow.evaluation.line_io import (
    line_evaluation_plan_to_dict,
    line_evaluation_report_to_dict,
    load_line_evaluation_plan,
    load_tracking_replay,
    tracking_replay_to_dict,
    write_line_evaluation_plan,
    write_line_evaluation_report,
    write_tracking_replay,
)
from hogflow.evaluation.line_positions import build_parser, main


def _fixed_evaluator() -> VirtualLinePositionEvaluator:
    return VirtualLinePositionEvaluator(
        monotonic_clock=lambda: 1.0,
        wall_clock=lambda: datetime(2026, 7, 26, tzinfo=timezone.utc),
    )


def test_plan_and_replay_json_round_trip(tmp_path: Path) -> None:
    plan = three_candidate_plan()
    replay = clean_pass_replay()
    plan_path = tmp_path / "plan.json"
    replay_path = tmp_path / "replay.json"

    write_line_evaluation_plan(plan, plan_path)
    write_tracking_replay(replay, replay_path)

    assert load_line_evaluation_plan(plan_path) == plan
    assert load_tracking_replay(replay_path) == replay
    assert json.loads(plan_path.read_text(encoding="utf-8")) == line_evaluation_plan_to_dict(plan)
    assert json.loads(replay_path.read_text(encoding="utf-8")) == tracking_replay_to_dict(replay)


def test_report_output_is_deterministic_and_path_free(tmp_path: Path) -> None:
    report = _fixed_evaluator().evaluate(three_candidate_plan(), clean_pass_replay())
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    first_report = write_line_evaluation_report(report, first)
    second_report = write_line_evaluation_report(report, second)
    first_text = first.read_text(encoding="utf-8")

    assert first_report == second_report
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first_text) == line_evaluation_report_to_dict(first_report)
    assert str(tmp_path) not in first_text
    assert "C:\\" not in first_text
    assert "/home/" not in first_text
    assert first_report.statistics.report_written


@pytest.mark.parametrize("document", ("plan", "replay"))
def test_unknown_schema_is_rejected(tmp_path: Path, document: str) -> None:
    path = tmp_path / f"{document}.json"
    payload = (
        line_evaluation_plan_to_dict(three_candidate_plan())
        if document == "plan"
        else tracking_replay_to_dict(clean_pass_replay())
    )
    payload["schema_version"] = "999"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(LineEvaluationSchemaError, match="unsupported"):
        (load_line_evaluation_plan(path) if document == "plan" else load_tracking_replay(path))


def test_malformed_replay_and_plan_are_sanitized(tmp_path: Path) -> None:
    malformed = tmp_path / "private user replay.json"
    malformed.write_text("{broken", encoding="utf-8")
    with pytest.raises(LineEvaluationSchemaError) as caught:
        load_tracking_replay(malformed)
    assert str(tmp_path) not in str(caught.value)

    plan_path = tmp_path / "plan.json"
    payload = line_evaluation_plan_to_dict(three_candidate_plan())
    payload["candidates"].append(payload["candidates"][0])
    plan_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(LineEvaluationSchemaError, match="invalid"):
        load_line_evaluation_plan(plan_path)


def test_report_write_failure_is_fatal_and_sanitized(tmp_path: Path) -> None:
    report = _fixed_evaluator().evaluate(three_candidate_plan(), clean_pass_replay())
    output_directory = tmp_path / "directory"
    output_directory.mkdir()

    with pytest.raises(LineEvaluationOutputError) as caught:
        write_line_evaluation_report(report, output_directory)

    assert str(tmp_path) not in str(caught.value)


def test_cli_help_describes_offline_evaluation() -> None:
    help_text = build_parser().format_help()

    assert "--replay" in help_text
    assert "--plan" in help_text
    assert "--output" in help_text
    assert "--matching-window-frames" in help_text
    assert "--ranking-method" in help_text
    assert "camera" in help_text.lower()


def test_cli_runs_synthetic_end_to_end_and_prints_sanitized_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan_path = tmp_path / "plan.json"
    replay_path = tmp_path / "replay.json"
    output_path = tmp_path / "report.json"
    write_line_evaluation_plan(three_candidate_plan(), plan_path)
    write_tracking_replay(clean_pass_replay(), replay_path)

    exit_code = main(
        (
            "--plan",
            str(plan_path),
            "--replay",
            str(replay_path),
            "--output",
            str(output_path),
            "--ranking-method",
            "event_f1",
            "--matching-window-frames",
            "2",
        )
    )

    stdout = capsys.readouterr().out
    summary = json.loads(stdout)
    report = json.loads(output_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert summary["recommended_candidate_id"] == "line-center"
    assert summary["report_written"] is True
    assert report["ranking"]["recommended_candidate_id"] == "line-center"
    assert str(tmp_path) not in stdout
    assert str(tmp_path) not in output_path.read_text(encoding="utf-8")
