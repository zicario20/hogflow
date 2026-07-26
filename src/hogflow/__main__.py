"""Command-line entry point for the local Operator MVP desktop."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from hogflow.application import OperatorInputError, VideoSourceRequest
from hogflow.bootstrap import compose_operator_desktop
from hogflow.camera import PreviewConfiguration
from hogflow.core import HogFlowError


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded Phase 9.4 executable parser."""

    parser = argparse.ArgumentParser(
        prog="hogflow",
        description="Run the local HogFlow Operator MVP with an optional shared source.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=("run",),
        help="Run the local Operator MVP desktop (default: run).",
    )
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument(
        "--camera",
        type=int,
        metavar="INDEX",
        help="Configure one local camera index without opening it during startup.",
    )
    sources.add_argument(
        "--video",
        metavar="FILE",
        help="Configure one existing local video file for deterministic validation.",
    )
    parser.add_argument(
        "--disable-preview",
        action="store_true",
        help="Disable the local latest-frame operator preview.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Compose and run the local desktop without opening resources on import/help."""

    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        source = None
        if arguments.camera is not None:
            source = VideoSourceRequest.camera(arguments.camera)
        elif arguments.video is not None:
            source = VideoSourceRequest.video_file(arguments.video)
        settings = {}
        if source is not None:
            settings["video_source"] = source
        if arguments.disable_preview:
            settings["preview_configuration"] = PreviewConfiguration(enabled=False)
        composition = compose_operator_desktop(**settings)
        composition.run()
    except (HogFlowError, OperatorInputError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
