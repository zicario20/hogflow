"""Framework-neutral baseline detector training contracts and orchestration."""

from hogflow.training.configuration import TrainingConfiguration
from hogflow.training.contracts import DetectorTrainer
from hogflow.training.dataset import load_prepared_training_dataset
from hogflow.training.models import (
    BaselineTrainingResult,
    DetectorTrainingOutput,
    DetectorValidationOutput,
    FailureAnalysisSummary,
    FrameworkMetric,
    PreparedTrainingDataset,
    TrainingMetrics,
    TrainingRunMetadata,
    ValidationPrediction,
)

__all__ = [
    "BaselineTrainingResult",
    "DetectorTrainer",
    "DetectorTrainingOutput",
    "DetectorValidationOutput",
    "FailureAnalysisSummary",
    "FrameworkMetric",
    "PreparedTrainingDataset",
    "TrainingConfiguration",
    "TrainingMetrics",
    "TrainingRunMetadata",
    "ValidationPrediction",
    "load_prepared_training_dataset",
]
