"""Framework-independent contract for replaceable detector trainers."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from hogflow.training.configuration import TrainingConfiguration
from hogflow.training.models import (
    DetectorTrainingOutput,
    DetectorValidationOutput,
    PreparedTrainingDataset,
)


class DetectorTrainer(Protocol):
    """Train and validate one replaceable object-detector implementation.

    Implementations own model loading, optimization, framework configuration,
    checkpoint creation, and prediction conversion. Callers provide only a
    validated HogFlow dataset and immutable configuration. No framework object
    may cross this boundary. Implementations need not be thread-safe and may
    use private mutable state during one local run.

    Expected dependency, configuration, dataset, and runtime failures should
    use documented HogFlow exceptions. The contract does not promise model
    quality, deterministic CUDA kernels, resume compatibility between framework
    versions, tracking behavior, or counting behavior.
    """

    @property
    def trainer_name(self) -> str:
        """Return a stable framework/adapter name for local provenance."""

        ...

    @property
    def trainer_version(self) -> str:
        """Return the concrete trainer framework version."""

        ...

    @property
    def model_reference(self) -> str:
        """Return a sanitized model name without a local directory."""

        ...

    def train(
        self,
        dataset: PreparedTrainingDataset,
        configuration: TrainingConfiguration,
        *,
        resume_checkpoint: Path | None = None,
    ) -> DetectorTrainingOutput:
        """Train locally and return only framework-neutral artifact metadata."""

        ...

    def validate(
        self,
        dataset: PreparedTrainingDataset,
        checkpoint_path: Path,
        configuration: TrainingConfiguration,
    ) -> DetectorValidationOutput:
        """Return framework-neutral predictions for deterministic evaluation."""

        ...


__all__ = ["DetectorTrainer"]
