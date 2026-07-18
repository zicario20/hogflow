"""Framework-neutral orchestration for one local baseline detector run."""

from __future__ import annotations

import subprocess
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from hogflow.annotation.validation import write_validation_reports
from hogflow.core import InputDataError
from hogflow.evaluation import evaluate_detections
from hogflow.training.configuration import TrainingConfiguration
from hogflow.training.contracts import DetectorTrainer
from hogflow.training.failure_analysis import summarize_detection_failures
from hogflow.training.models import (
    BaselineTrainingResult,
    PreparedTrainingDataset,
    TrainingMetrics,
    TrainingRunMetadata,
)
from hogflow.training.reporting import write_training_reports


def run_baseline_training(
    trainer: DetectorTrainer,
    dataset: PreparedTrainingDataset,
    configuration: TrainingConfiguration,
    *,
    output_root: str | Path,
    repository_root: str | Path,
    resume_checkpoint: Path | None = None,
) -> BaselineTrainingResult:
    """Train, validate, evaluate, and report one local detector baseline.

    The trainer supplies framework-neutral predictions. HogFlow computes
    precision, recall, F1, and IoU using the approved Phase 4.1 evaluator.
    Framework metrics remain separately named and are never substituted for
    the HogFlow result.
    """

    if not isinstance(dataset, PreparedTrainingDataset):
        raise InputDataError("dataset must be PreparedTrainingDataset.")
    if not isinstance(configuration, TrainingConfiguration):
        raise InputDataError("configuration must be TrainingConfiguration.")
    local_output_root = Path(output_root)

    write_validation_reports(
        dataset.validation_report,
        local_output_root / "evaluation" / configuration.run_name / "annotation_validation.json",
    )
    training = trainer.train(
        dataset,
        configuration,
        resume_checkpoint=resume_checkpoint,
    )
    validation = trainer.validate(
        dataset,
        training.best_checkpoint_path,
        configuration,
    )
    evaluation = evaluate_detections(
        validation.frames,
        iou_threshold=configuration.iou_threshold,
    )
    mean_iou = (
        sum(match.iou for match in evaluation.matches) / len(evaluation.matches)
        if evaluation.matches
        else 0.0
    )
    metrics = TrainingMetrics(
        hogflow=evaluation,
        mean_matched_iou=mean_iou,
        framework=validation.framework_metrics,
    )
    failure_analysis = summarize_detection_failures(
        validation.frames,
        evaluation,
        small_object_area_ratio=configuration.small_object_area_ratio,
    )
    code_version, git_commit = collect_code_provenance(repository_root)
    metadata = TrainingRunMetadata(
        run_id=training.run_id,
        dataset_id=dataset.manifest.dataset_id,
        dataset_version=dataset.dataset_version,
        code_version=code_version,
        git_commit=git_commit,
        trainer_name=trainer.trainer_name,
        trainer_version=trainer.trainer_version,
        model_reference=trainer.model_reference,
        configuration=configuration,
        best_checkpoint_relative_path=_checkpoint_relative_path(
            training.best_checkpoint_path,
            local_output_root,
        ),
        determinism_notes=_determinism_notes(configuration),
    )
    metadata_path, metrics_path, failure_path = write_training_reports(
        local_output_root,
        metadata,
        training,
        metrics,
        failure_analysis,
    )
    return BaselineTrainingResult(
        training=training,
        metrics=metrics,
        failure_analysis=failure_analysis,
        metadata_path=metadata_path,
        metrics_path=metrics_path,
        failure_report_path=failure_path,
    )


def collect_code_provenance(repository_root: str | Path) -> tuple[str, str]:
    """Return installed package version and Git commit without recording paths."""

    try:
        code_version = version("hogflow")
    except PackageNotFoundError:
        code_version = "source-tree"
    resolved_repository = Path(repository_root).resolve()
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={resolved_repository.as_posix()}",
                "rev-parse",
                "HEAD",
            ],
            cwd=resolved_repository,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InputDataError(
            "Unable to determine the local Git commit for training metadata."
        ) from exc
    commit = result.stdout.strip()
    if (
        result.returncode != 0
        or len(commit) != 40
        or any(character not in "0123456789abcdef" for character in commit)
    ):
        raise InputDataError("Unable to determine the local Git commit for training metadata.")
    return code_version, commit


def _checkpoint_relative_path(checkpoint: Path, output_root: Path) -> str:
    try:
        relative = checkpoint.resolve().relative_to(output_root.resolve())
    except ValueError as exc:
        raise InputDataError(
            "Best checkpoint must remain inside the local training output root."
        ) from exc
    return relative.as_posix()


def _determinism_notes(configuration: TrainingConfiguration) -> tuple[str, ...]:
    notes = [
        "The configured seed is recorded and passed to the concrete trainer.",
        "Dataset ordering and HogFlow evaluation are deterministic for identical inputs.",
    ]
    if configuration.device.lower() != "cpu":
        notes.append(
            "CUDA kernels and hardware-dependent operations may remain nondeterministic despite deterministic mode."
        )
    else:
        notes.append("CPU execution is the Phase 4.3 reproducibility default.")
    return tuple(notes)


__all__ = ["collect_code_provenance", "run_baseline_training"]
