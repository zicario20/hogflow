"""Immutable framework-neutral models for detector training and validation."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from re import fullmatch

from hogflow.annotation.models import AnnotationDatasetManifest, DatasetSplit
from hogflow.annotation.validation import AnnotationValidationReport
from hogflow.core import InputDataError
from hogflow.evaluation import DetectionEvaluationResult, DetectionFrame
from hogflow.models import BoundingBox
from hogflow.training.configuration import TrainingConfiguration


def _non_negative_integer(value: object, *, field_name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InputDataError(f"{field_name} must be a non-negative integer.")


def _finite_number(value: object, *, field_name: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
        raise InputDataError(f"{field_name} must be a finite number.")


@dataclass(frozen=True, slots=True)
class FrameworkMetric:
    """One explicitly framework-owned scalar metric retained by name."""

    name: str
    value: float

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise InputDataError("Framework metric name must be non-empty text.")
        _finite_number(self.value, field_name="Framework metric value")


@dataclass(frozen=True, slots=True)
class ValidationPrediction:
    """One pixel-space detector prediction after a framework boundary."""

    bounding_box: BoundingBox
    confidence: float
    class_name: str = "pig"

    def __post_init__(self) -> None:
        if not isinstance(self.bounding_box, BoundingBox):
            raise InputDataError("Validation prediction requires a canonical BoundingBox.")
        _finite_number(self.confidence, field_name="Validation prediction confidence")
        if not 0.0 <= self.confidence <= 1.0:
            raise InputDataError("Validation prediction confidence must be between 0 and 1.")
        if self.class_name != "pig":
            raise InputDataError("Phase 4.3 validation supports only the pig class.")


@dataclass(frozen=True, slots=True)
class PreparedTrainingDataset:
    """Validated local training input expressed through opaque manifest records.

    ``root`` and ``manifest_path`` are local runtime locations and are never
    included in sanitized training reports. The dataset version fingerprints
    the sanitized manifest, image checksums, and validated YOLO label content.
    """

    root: Path
    manifest_path: Path
    manifest: AnnotationDatasetManifest
    validation_report: AnnotationValidationReport
    dataset_version: str
    train_frame_ids: tuple[str, ...]
    validation_frame_ids: tuple[str, ...]
    test_frame_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.root, Path) or not isinstance(self.manifest_path, Path):
            raise InputDataError("Prepared dataset locations must be pathlib Paths.")
        if not isinstance(self.manifest, AnnotationDatasetManifest):
            raise InputDataError("manifest must be AnnotationDatasetManifest.")
        if not isinstance(self.validation_report, AnnotationValidationReport):
            raise InputDataError("validation_report must be AnnotationValidationReport.")
        if not self.validation_report.valid:
            raise InputDataError("Prepared training dataset must pass annotation validation.")
        if fullmatch(r"[0-9a-f]{64}", self.dataset_version) is None:
            raise InputDataError("dataset_version must be a SHA-256 hexadecimal digest.")
        all_ids: list[str] = []
        for field_name in (
            "train_frame_ids",
            "validation_frame_ids",
            "test_frame_ids",
        ):
            identifiers = getattr(self, field_name)
            if not isinstance(identifiers, tuple) or tuple(sorted(identifiers)) != identifiers:
                raise InputDataError(f"{field_name} must be a sorted immutable tuple.")
            all_ids.extend(identifiers)
        if len(set(all_ids)) != len(all_ids):
            raise InputDataError("A prepared frame may belong to only one dataset split.")
        if not self.train_frame_ids or not self.validation_frame_ids:
            raise InputDataError(
                "Prepared training requires non-empty train and validation splits."
            )

    def frame_ids_for(self, split: DatasetSplit) -> tuple[str, ...]:
        """Return immutable frame IDs for one supported evaluation split."""

        if split is DatasetSplit.TRAIN:
            return self.train_frame_ids
        if split is DatasetSplit.VALIDATION:
            return self.validation_frame_ids
        if split is DatasetSplit.TEST:
            return self.test_frame_ids
        raise InputDataError("The preparation split cannot be used for detector training.")


@dataclass(frozen=True, slots=True)
class DetectorTrainingOutput:
    """Framework-neutral artifacts returned after one trainer invocation."""

    run_id: str
    best_checkpoint_path: Path
    framework_metrics: tuple[FrameworkMetric, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.run_id, str)
            or fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", self.run_id) is None
        ):
            raise InputDataError("run_id must be an opaque identifier.")
        if not isinstance(self.best_checkpoint_path, Path):
            raise InputDataError("best_checkpoint_path must be a pathlib Path.")
        if not isinstance(self.framework_metrics, tuple) or not all(
            isinstance(item, FrameworkMetric) for item in self.framework_metrics
        ):
            raise InputDataError("framework_metrics must be an immutable FrameworkMetric tuple.")
        names = tuple(item.name for item in self.framework_metrics)
        if tuple(sorted(names)) != names or len(set(names)) != len(names):
            raise InputDataError("framework_metrics must have unique names in sorted order.")


@dataclass(frozen=True, slots=True)
class DetectorValidationOutput:
    """Framework-neutral predictions and separate framework validation metrics."""

    frames: tuple[DetectionFrame, ...]
    framework_metrics: tuple[FrameworkMetric, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.frames, tuple) or not all(
            isinstance(frame, DetectionFrame) for frame in self.frames
        ):
            raise InputDataError("frames must be an immutable DetectionFrame tuple.")
        frame_keys = tuple((frame.source_video_id, frame.frame_id) for frame in self.frames)
        if tuple(sorted(frame_keys)) != frame_keys or len(set(frame_keys)) != len(frame_keys):
            raise InputDataError("Validation frames must be unique and deterministically sorted.")
        if not isinstance(self.framework_metrics, tuple) or not all(
            isinstance(item, FrameworkMetric) for item in self.framework_metrics
        ):
            raise InputDataError("framework_metrics must be an immutable FrameworkMetric tuple.")


@dataclass(frozen=True, slots=True)
class TrainingMetrics:
    """HogFlow metrics separated explicitly from framework-owned metrics."""

    hogflow: DetectionEvaluationResult
    mean_matched_iou: float
    framework: tuple[FrameworkMetric, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.hogflow, DetectionEvaluationResult):
            raise InputDataError("hogflow metrics must be DetectionEvaluationResult.")
        _finite_number(self.mean_matched_iou, field_name="mean_matched_iou")
        if not 0.0 <= self.mean_matched_iou <= 1.0:
            raise InputDataError("mean_matched_iou must be between 0 and 1.")
        if not isinstance(self.framework, tuple) or not all(
            isinstance(item, FrameworkMetric) for item in self.framework
        ):
            raise InputDataError("framework metrics must be an immutable tuple.")


@dataclass(frozen=True, slots=True)
class FailureAnalysisSummary:
    """Deterministic detection failures available from Phase 4.2 annotations."""

    false_positive_count: int
    false_negative_count: int
    very_small_ground_truth_count: int
    empty_frame_count: int
    empty_frame_false_positive_count: int
    heavy_occlusion_count: int | None
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "false_positive_count",
            "false_negative_count",
            "very_small_ground_truth_count",
            "empty_frame_count",
            "empty_frame_false_positive_count",
        ):
            _non_negative_integer(getattr(self, field_name), field_name=field_name)
        if self.heavy_occlusion_count is not None:
            _non_negative_integer(self.heavy_occlusion_count, field_name="heavy_occlusion_count")
        if not isinstance(self.notes, tuple) or not all(
            isinstance(note, str) and note.strip() for note in self.notes
        ):
            raise InputDataError("notes must be an immutable tuple of non-empty text.")


@dataclass(frozen=True, slots=True)
class TrainingRunMetadata:
    """Sanitized reproducibility metadata containing no local dataset paths."""

    run_id: str
    dataset_id: str
    dataset_version: str
    code_version: str
    git_commit: str
    trainer_name: str
    trainer_version: str
    model_reference: str
    configuration: TrainingConfiguration
    best_checkpoint_relative_path: str
    determinism_notes: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "run_id",
            "dataset_id",
            "code_version",
            "git_commit",
            "trainer_name",
            "trainer_version",
            "model_reference",
            "best_checkpoint_relative_path",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise InputDataError(f"{field_name} must be non-empty text.")
        if fullmatch(r"[0-9a-f]{64}", self.dataset_version) is None:
            raise InputDataError("dataset_version must be a SHA-256 digest.")
        if not isinstance(self.configuration, TrainingConfiguration):
            raise InputDataError("configuration must be TrainingConfiguration.")
        if any(separator in self.model_reference for separator in ("/", "\\")):
            raise InputDataError("model_reference must be a sanitized filename.")
        if ":" in self.model_reference:
            raise InputDataError("model_reference must not contain an absolute-path prefix.")
        checkpoint = Path(self.best_checkpoint_relative_path)
        if (
            checkpoint.is_absolute()
            or ".." in checkpoint.parts
            or "\\" in self.best_checkpoint_relative_path
            or ":" in self.best_checkpoint_relative_path
        ):
            raise InputDataError("Checkpoint metadata path must remain output-relative.")
        if not isinstance(self.determinism_notes, tuple):
            raise InputDataError("determinism_notes must be an immutable tuple.")


@dataclass(frozen=True, slots=True)
class BaselineTrainingResult:
    """Completed local baseline result and its local report locations."""

    training: DetectorTrainingOutput
    metrics: TrainingMetrics
    failure_analysis: FailureAnalysisSummary
    metadata_path: Path
    metrics_path: Path
    failure_report_path: Path


__all__ = [
    "BaselineTrainingResult",
    "DetectorTrainingOutput",
    "DetectorValidationOutput",
    "FailureAnalysisSummary",
    "FrameworkMetric",
    "PreparedTrainingDataset",
    "TrainingMetrics",
    "TrainingRunMetadata",
    "ValidationPrediction",
]
