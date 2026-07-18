"""Immutable framework-neutral configuration for baseline detector training."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from re import fullmatch

from hogflow.annotation.models import DatasetSplit
from hogflow.core import ConfigurationError


def _positive_integer(value: object, *, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigurationError(f"{field_name} must be a positive integer.")
    return value


def _probability(value: object, *, field_name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or not 0.0 < float(value) <= 1.0
    ):
        raise ConfigurationError(f"{field_name} must be greater than 0 and at most 1.")
    return float(value)


@dataclass(frozen=True, slots=True)
class TrainingConfiguration:
    """Reproducible detector-training settings independent of a model framework.

    The defaults favor repeatability and a bounded baseline experiment. CPU is
    the default device and data-loader workers default to zero. CUDA may still
    contain nondeterministic operations even when ``deterministic`` is true.
    """

    epochs: int = 25
    batch_size: int = 8
    image_size: int = 640
    device: str = "cpu"
    optimizer: str = "AdamW"
    workers: int = 0
    seed: int = 42
    deterministic: bool = True
    confidence_threshold: float = 0.25
    iou_threshold: float = 0.5
    small_object_area_ratio: float = 0.01
    evaluation_split: DatasetSplit = DatasetSplit.VALIDATION
    run_name: str = "phase4-3-baseline"

    def __post_init__(self) -> None:
        _positive_integer(self.epochs, field_name="epochs")
        if self.epochs > 30:
            raise ConfigurationError("Phase 4.3 epochs must not exceed 30.")
        _positive_integer(self.batch_size, field_name="batch_size")
        _positive_integer(self.image_size, field_name="image_size")
        if not isinstance(self.device, str) or not self.device.strip():
            raise ConfigurationError("device must be non-empty text.")
        if not isinstance(self.optimizer, str) or not self.optimizer.strip():
            raise ConfigurationError("optimizer must be non-empty text.")
        if not isinstance(self.workers, int) or isinstance(self.workers, bool) or self.workers < 0:
            raise ConfigurationError("workers must be a non-negative integer.")
        if not isinstance(self.seed, int) or isinstance(self.seed, bool) or self.seed < 0:
            raise ConfigurationError("seed must be a non-negative integer.")
        if not isinstance(self.deterministic, bool):
            raise ConfigurationError("deterministic must be a boolean.")
        object.__setattr__(
            self,
            "confidence_threshold",
            _probability(self.confidence_threshold, field_name="confidence_threshold"),
        )
        object.__setattr__(
            self,
            "iou_threshold",
            _probability(self.iou_threshold, field_name="iou_threshold"),
        )
        object.__setattr__(
            self,
            "small_object_area_ratio",
            _probability(self.small_object_area_ratio, field_name="small_object_area_ratio"),
        )
        if self.evaluation_split not in {DatasetSplit.VALIDATION, DatasetSplit.TEST}:
            raise ConfigurationError("evaluation_split must be validation or test.")
        if (
            not isinstance(self.run_name, str)
            or fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", self.run_name) is None
        ):
            raise ConfigurationError(
                "run_name must contain only letters, numbers, underscores, or hyphens."
            )


def evaluation_split_from_string(value: str) -> DatasetSplit:
    """Convert a CLI value to an approved detector-evaluation split."""

    try:
        split = DatasetSplit(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("Evaluation split must be validation or test.") from exc
    if split not in {DatasetSplit.VALIDATION, DatasetSplit.TEST}:
        raise ConfigurationError("Evaluation split must be validation or test.")
    return split


__all__ = ["TrainingConfiguration", "evaluation_split_from_string"]
