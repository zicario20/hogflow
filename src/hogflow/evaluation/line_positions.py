"""Offline CLI for deterministic virtual-line candidate evaluation."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from hogflow.core import HogFlowError, configure_logging, get_logger
from hogflow.evaluation.line_evaluator import VirtualLinePositionEvaluator
from hogflow.evaluation.line_io import (
    load_line_evaluation_plan,
    load_tracking_replay,
    override_plan_options,
    write_line_evaluation_report,
)
from hogflow.evaluation.line_models import LineRankingMethod

LOGGER = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Create the headless Phase 6 offline evaluation parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Evaluate normalized virtual-line candidates from a local tracking replay. "
            "No camera, detector, tracking framework, or accumulated count is used."
        )
    )
    parser.add_argument("--replay", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--ranking-method",
        choices=tuple(method.value for method in LineRankingMethod),
    )
    parser.add_argument("--matching-window-frames", type=int)
    parser.add_argument(
        "--human-summary",
        action="store_true",
        help="Print a short sanitized human-readable summary after the JSON summary.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Evaluate one local replay and write one sanitized report."""

    configure_logging()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        plan = load_line_evaluation_plan(arguments.plan)
        plan = override_plan_options(
            plan,
            ranking_method=(
                None
                if arguments.ranking_method is None
                else LineRankingMethod(arguments.ranking_method)
            ),
            matching_window_frames=arguments.matching_window_frames,
        )
        replay = load_tracking_replay(arguments.replay)
        report = VirtualLinePositionEvaluator().evaluate(plan, replay)
        report = write_line_evaluation_report(report, arguments.output)
    except HogFlowError as exc:
        parser.error(str(exc))

    summary = {
        "candidate_ids": [result.candidate_id for result in report.candidate_results],
        "evidence_level": report.evidence_level.value,
        "ground_truth_available": report.ground_truth_available,
        "plan_id": report.plan.plan_id,
        "ranking_method": report.ranking_method.value,
        "recommended_candidate_id": report.recommended_candidate_id,
        "replay_id": report.replay_id,
        "report_written": report.statistics.report_written,
        "warnings": list(report.warnings),
    }
    print(json.dumps(summary, sort_keys=True))
    if arguments.human_summary:
        print(
            f"Evaluated {len(report.candidate_results)} candidates; "
            f"recommendation={report.recommended_candidate_id or 'none'}; "
            f"evidence={report.evidence_level.value}."
        )
    LOGGER.info(
        "Line-position evaluation completed for %d candidates.",
        len(report.candidate_results),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
