"""Immutable framework-neutral configuration for baseline detector training."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from math import isfinite
from re import fullmatch

from hogflow.annotation.models import DatasetSplit
from hogflow.core import ConfigurationError


class TrainingProfile(str, Enum):
    """Explicit training policy supported by the existing trainer boundary."""

    PHASE_4_3_BASELINE = "phase4_3_baseline"
    PHASE_10_3A_DEMO = "phase10_3a_demo"


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
    profile: TrainingProfile = TrainingProfile.PHASE_4_3_BASELINE
    early_stopping_patience: int | None = None
    augmentation: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        _positive_integer(self.epochs, field_name="epochs")
        if not isinstance(self.profile, TrainingProfile):
            raise ConfigurationError("profile must be a TrainingProfile value.")
        maximum_epochs = 100 if self.profile is TrainingProfile.PHASE_10_3A_DEMO else 30
        if self.epochs > maximum_epochs:
            raise ConfigurationError(
                f"{self.profile.value} epochs must not exceed {maximum_epochs}."
            )
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
        if self.early_stopping_patience is not None:
            _positive_integer(self.early_stopping_patience, field_name="early_stopping_patience")
        if (
            self.profile is TrainingProfile.PHASE_10_3A_DEMO
            and self.early_stopping_patience is None
        ):
            object.__setattr__(self, "early_stopping_patience", 20)
        if not isinstance(self.augmentation, tuple):
            raise ConfigurationError("augmentation must be an immutable tuple of settings.")
        augmentation_names: list[str] = []
        for item in self.augmentation:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], str)
                or not item[0].strip()
                or not isinstance(item[1], (int, float))
                or isinstance(item[1], bool)
                or not isfinite(float(item[1]))
                or float(item[1]) < 0.0
            ):
                raise ConfigurationError(
                    "augmentation entries must be (name, finite non-negative number) tuples."
                )
            augmentation_names.append(item[0])
        if tuple(sorted(augmentation_names)) != tuple(augmentation_names) or len(
            set(augmentation_names)
        ) != len(augmentation_names):
            raise ConfigurationError("augmentation names must be unique and sorted.")
        if (
            not isinstance(self.run_name, str)
            or fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", self.run_name) is None
        ):
            raise ConfigurationError(
                "run_name must contain only letters, numbers, underscores, or hyphens."
            )

    @classmethod
    def demo_phase_10_3a(
        cls,
        *,
        epochs: int = 90,
        batch_size: int = 8,
        image_size: int = 640,
        device: str = "cpu",
        optimizer: str = "AdamW",
        workers: int = 0,
        seed: int = 42,
        deterministic: bool = True,
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.5,
        small_object_area_ratio: float = 0.01,
        evaluation_split: DatasetSplit = DatasetSplit.VALIDATION,
        run_name: str = "phase10-3a-demo",
        patience: int = 20,
    ) -> "TrainingConfiguration":
        """Create the bounded, reproducible Phase 10.3A demo profile."""

        return cls(
            epochs=epochs,
            batch_size=batch_size,
            image_size=image_size,
            device=device,
            optimizer=optimizer,
            workers=workers,
            seed=seed,
            deterministic=deterministic,
            confidence_threshold=confidence_threshold,
            iou_threshold=iou_threshold,
            small_object_area_ratio=small_object_area_ratio,
            evaluation_split=evaluation_split,
            run_name=run_name,
            profile=TrainingProfile.PHASE_10_3A_DEMO,
            early_stopping_patience=patience,
            augmentation=(
                ("close_mosaic", 10.0),
                ("fliplr", 0.5),
                ("hsv_h", 0.015),
                ("hsv_s", 0.4),
                ("hsv_v", 0.3),
                ("mosaic", 0.5),
                ("scale", 0.4),
                ("translate", 0.1),
            ),
        )

    @property
    def augmentation_settings(self) -> dict[str, float]:
        """Return the immutable augmentation tuple as a framework argument map."""

        return {name: value for name, value in self.augmentation}

    @property
    def configuration_fingerprint(self) -> str:
        """Return a stable SHA-256 fingerprint of every effective setting."""

        payload = {
            "augmentation": dict(self.augmentation),
            "batch_size": self.batch_size,
            "confidence_threshold": self.confidence_threshold,
            "deterministic": self.deterministic,
            "device": self.device,
            "early_stopping_patience": self.early_stopping_patience,
            "epochs": self.epochs,
            "evaluation_split": self.evaluation_split.value,
            "image_size": self.image_size,
            "iou_threshold": self.iou_threshold,
            "optimizer": self.optimizer,
            "profile": self.profile.value,
            "run_name": self.run_name,
            "seed": self.seed,
            "small_object_area_ratio": self.small_object_area_ratio,
            "workers": self.workers,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluation_split_from_string(value: str) -> DatasetSplit:
    """Convert a CLI value to an approved detector-evaluation split."""

    try:
        split = DatasetSplit(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("Evaluation split must be validation or test.") from exc
    if split not in {DatasetSplit.VALIDATION, DatasetSplit.TEST}:
        raise ConfigurationError("Evaluation split must be validation or test.")
    return split


__all__ = ["TrainingConfiguration", "TrainingProfile", "evaluation_split_from_string"]
