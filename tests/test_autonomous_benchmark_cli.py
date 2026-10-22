from __future__ import annotations

from hogflow import __main__ as cli


def test_parser_exposes_autonomous_benchmark_and_report_root() -> None:
    arguments = cli.build_parser().parse_args(
        ["autonomous-demo", "--video", "demo.mp4", "--benchmark", "--report-root", "reports"]
    )

    assert arguments.benchmark is True
    assert arguments.report_root.name == "reports"
