"""Command-line entry point for the local Operator MVP desktop."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from hogflow.bootstrap import compose_operator_desktop


def build_parser() -> argparse.ArgumentParser:
    """Build the bounded Phase 9.2 executable parser."""

    parser = argparse.ArgumentParser(
        prog="hogflow",
        description="Run the local, manual-refresh HogFlow Operator MVP.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=("run",),
        help="Run the local Operator MVP desktop (default: run).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Compose and run the local desktop without camera or network resources."""

    build_parser().parse_args(argv)
    compose_operator_desktop().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
