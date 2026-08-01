"""Headless local CLI for the Phase 10.3 validation hard gate and reports."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from hogflow.core import HogFlowError
from hogflow.data import VideoInspectionSettings
from hogflow.validation import (
    GitRepositoryPolicy,
    LocalValidationWorkspace,
    ModelGateState,
    RealWorldValidationWorkflow,
    ValidationConfigurationError,
    write_validation_report,
)
from hogflow.video.metadata import OpenCVVideoMetadataReader


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m hogflow.video.real_world_validation_cli",
        description=(
            "Verify authorized local Phase 10.3 evidence and write sanitized offline reports. "
            "This command does not download models or claim pig-count accuracy."
        ),
    )
    parser.add_argument(
        "--output-directory",
        default="data/evaluation/phase10_3",
        help="Ignored repository-relative directory for local JSON and Markdown reports.",
    )
    parser.add_argument(
        "--model-path",
        help="Optional explicit ignored repository-relative model artifact in an approved model root.",
    )
    parser.add_argument(
        "--metadata-samples",
        type=int,
        default=12,
        help="Bounded metadata/stability sample count (default: 12).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path.cwd().resolve()
    try:
        if not (root / "pyproject.toml").is_file() or not (root / "src" / "hogflow").is_dir():
            parser.error("Run this command from the HogFlow repository root.")
        output = _local_output_path(root, args.output_directory)
        git_policy = GitRepositoryPolicy(root)
        if not git_policy.is_ignored(output / "validation_report.json"):
            parser.error("Validation output must remain under an ignored local path.")
        workspace = LocalValidationWorkspace(
            root,
            OpenCVVideoMetadataReader(
                VideoInspectionSettings(sample_frame_count=args.metadata_samples)
            ),
            git_policy=git_policy,
        )
        videos = workspace.inspect_authorized_videos()
        model = workspace.locate_model(args.model_path)
        if model.state is ModelGateState.AVAILABLE:
            parser.error(
                "A compatible local model passed the gate, but a calibrated model-present "
                "execution must be supplied through the Phase 10.3 backend boundary."
            )
        report = RealWorldValidationWorkflow().run(
            workspace=workspace,
            inspected_videos=videos,
            model_availability=model,
        )
        write_validation_report(
            report,
            json_path=output / "validation_report.json",
            markdown_path=output / "validation_report.md",
        )
        print(
            json.dumps(
                {
                    "empirical_verdict": report.empirical_verdict,
                    "model_gate": report.model_availability.state.value,
                    "report_fingerprint": report.report_fingerprint,
                    "results": [
                        {
                            "status": item.status.value,
                            "video_id": item.video.video_id,
                        }
                        for item in report.results
                    ],
                },
                sort_keys=True,
            )
        )
        return 0
    except HogFlowError as exc:
        parser.error(str(exc))
    return 2


def _local_output_path(root: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValidationConfigurationError("Output directory must be repository-relative text.")
    requested = Path(value)
    if requested.is_absolute() or ".." in requested.parts:
        raise ValidationConfigurationError(
            "Output directory must be repository-relative without traversal."
        )
    output = (root / requested).resolve()
    allowed = tuple(
        (root / name).resolve() for name in ("data/evaluation", "data/runs", "data/metrics")
    )
    if not any(_within(output, base) for base in allowed):
        raise ValidationConfigurationError(
            "Output directory must be inside an approved ignored validation root."
        )
    return output


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
