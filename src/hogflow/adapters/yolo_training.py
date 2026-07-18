"""Local CLI composition root for the Phase 4.3 YOLO baseline."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from hogflow.adapters.yolo_baseline_trainer import YOLOBaselineTrainer
from hogflow.core import HogFlowError, configure_logging, get_logger
from hogflow.training.baseline import run_baseline_training
from hogflow.training.configuration import (
    TrainingConfiguration,
    evaluation_split_from_string,
)
from hogflow.training.dataset import load_prepared_training_dataset

LOGGER = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Create the Phase 4.3 local baseline-training parser."""

    parser = argparse.ArgumentParser(
        description="Train one local replaceable pig-detector baseline from a validated dataset."
    )
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("data"))
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--optimizer", default="AdamW")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--deterministic",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--confidence", type=float, default=0.25)
    parser.add_argument("--iou-threshold", type=float, default=0.5)
    parser.add_argument("--small-object-area-ratio", type=float, default=0.01)
    parser.add_argument(
        "--evaluation-split",
        choices=("validation", "test"),
        default="validation",
    )
    parser.add_argument("--run-name", default="phase4-3-baseline")
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one local baseline and return a process status code."""

    configure_logging()
    parser = build_parser()
    arguments = parser.parse_args(argv)
    manifest_path = arguments.manifest or (arguments.dataset / "metadata" / "dataset_manifest.json")
    try:
        configuration = TrainingConfiguration(
            epochs=arguments.epochs,
            batch_size=arguments.batch_size,
            image_size=arguments.image_size,
            device=arguments.device,
            optimizer=arguments.optimizer,
            workers=arguments.workers,
            seed=arguments.seed,
            deterministic=arguments.deterministic,
            confidence_threshold=arguments.confidence,
            iou_threshold=arguments.iou_threshold,
            small_object_area_ratio=arguments.small_object_area_ratio,
            evaluation_split=evaluation_split_from_string(arguments.evaluation_split),
            run_name=arguments.run_name,
        )
        dataset = load_prepared_training_dataset(arguments.dataset, manifest_path)
        trainer = YOLOBaselineTrainer(
            arguments.model,
            arguments.output_root,
        )
        result = run_baseline_training(
            trainer,
            dataset,
            configuration,
            output_root=arguments.output_root,
            repository_root=arguments.repository,
            resume_checkpoint=arguments.resume,
        )
    except (HogFlowError, ValueError) as exc:
        parser.error(str(exc))
    LOGGER.info(
        "Baseline run %s complete: precision=%.4f recall=%.4f f1=%.4f mean_iou=%.4f",
        result.training.run_id,
        result.metrics.hogflow.precision,
        result.metrics.hogflow.recall,
        result.metrics.hogflow.f1_score,
        result.metrics.mean_matched_iou,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["build_parser", "main"]
