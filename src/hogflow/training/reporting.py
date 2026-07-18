"""Deterministic local-only metadata, metrics, and failure reporting."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from hogflow.core import InputDataError
from hogflow.training.models import (
    DetectorTrainingOutput,
    FailureAnalysisSummary,
    TrainingMetrics,
    TrainingRunMetadata,
)


def write_training_reports(
    output_root: str | Path,
    metadata: TrainingRunMetadata,
    training: DetectorTrainingOutput,
    metrics: TrainingMetrics,
    failure_analysis: FailureAnalysisSummary,
) -> tuple[Path, Path, Path]:
    """Write sanitized run metadata, metrics, and failure analysis atomically."""

    if not isinstance(metadata, TrainingRunMetadata):
        raise InputDataError("metadata must be TrainingRunMetadata.")
    if not isinstance(training, DetectorTrainingOutput):
        raise InputDataError("training must be DetectorTrainingOutput.")
    if not isinstance(metrics, TrainingMetrics):
        raise InputDataError("metrics must be TrainingMetrics.")
    if not isinstance(failure_analysis, FailureAnalysisSummary):
        raise InputDataError("failure_analysis must be FailureAnalysisSummary.")

    report_root = Path(output_root) / "metrics" / metadata.run_id
    metadata_path = report_root / "training_metadata.json"
    metrics_path = report_root / "detection_metrics.json"
    failure_path = report_root / "failure_analysis.md"
    _atomic_write_json(metadata_path, _metadata_payload(metadata))
    _atomic_write_json(metrics_path, _metrics_payload(training, metrics))
    _atomic_write_text(failure_path, _failure_markdown(metadata, failure_analysis))
    return metadata_path, metrics_path, failure_path


def _metadata_payload(metadata: TrainingRunMetadata) -> dict[str, Any]:
    configuration = metadata.configuration
    return {
        "best_checkpoint_relative_path": metadata.best_checkpoint_relative_path,
        "code_version": metadata.code_version,
        "configuration": {
            "batch_size": configuration.batch_size,
            "confidence_threshold": configuration.confidence_threshold,
            "deterministic": configuration.deterministic,
            "device": configuration.device,
            "epochs": configuration.epochs,
            "evaluation_split": configuration.evaluation_split.value,
            "image_size": configuration.image_size,
            "iou_threshold": configuration.iou_threshold,
            "optimizer": configuration.optimizer,
            "run_name": configuration.run_name,
            "seed": configuration.seed,
            "small_object_area_ratio": configuration.small_object_area_ratio,
            "workers": configuration.workers,
        },
        "dataset_id": metadata.dataset_id,
        "dataset_version": metadata.dataset_version,
        "determinism_notes": list(metadata.determinism_notes),
        "format_version": 1,
        "git_commit": metadata.git_commit,
        "model_reference": metadata.model_reference,
        "run_id": metadata.run_id,
        "trainer_name": metadata.trainer_name,
        "trainer_version": metadata.trainer_version,
    }


def _metrics_payload(
    training: DetectorTrainingOutput,
    metrics: TrainingMetrics,
) -> dict[str, Any]:
    hogflow = metrics.hogflow
    return {
        "format_version": 1,
        "framework_training_metrics": {
            item.name: item.value for item in training.framework_metrics
        },
        "framework_validation_metrics": {item.name: item.value for item in metrics.framework},
        "hogflow_metrics": {
            "evaluated_frame_count": hogflow.evaluated_frame_count,
            "f1_score": hogflow.f1_score,
            "false_negatives": hogflow.false_negatives,
            "false_positives": hogflow.false_positives,
            "iou_threshold": hogflow.iou_threshold,
            "mean_matched_iou": metrics.mean_matched_iou,
            "precision": hogflow.precision,
            "recall": hogflow.recall,
            "true_positives": hogflow.true_positives,
        },
        "metric_boundary": {
            "framework": "Framework-reported values, including mAP when supplied by the trainer.",
            "hogflow": "Deterministic Phase 4.1 one-to-one metrics over framework-neutral predictions.",
        },
        "run_id": training.run_id,
    }


def _failure_markdown(
    metadata: TrainingRunMetadata,
    summary: FailureAnalysisSummary,
) -> str:
    occlusion = (
        str(summary.heavy_occlusion_count)
        if summary.heavy_occlusion_count is not None
        else "Unavailable from current annotations"
    )
    lines = [
        "# HogFlow Phase 4.3 Detection Failure Analysis",
        "",
        f"Run ID: `{metadata.run_id}`",
        "",
        "## Observable results",
        "",
        f"- False positives: {summary.false_positive_count}",
        f"- False negatives: {summary.false_negative_count}",
        f"- Very small ground-truth pigs: {summary.very_small_ground_truth_count}",
        f"- Human-verified empty frames: {summary.empty_frame_count}",
        f"- Predictions on empty frames: {summary.empty_frame_false_positive_count}",
        f"- Heavy occlusions: {occlusion}",
        "",
        "## Interpretation limits",
        "",
    ]
    lines.extend(f"- {note}" for note in summary.notes)
    lines.extend(
        [
            "",
            "This local report is detector diagnostic evidence only. It does not establish pig-counting accuracy, operational performance, or production readiness.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write_text(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
    )


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise InputDataError("Unable to write local training report output.") from exc


__all__ = ["write_training_reports"]
