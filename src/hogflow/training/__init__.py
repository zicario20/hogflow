"""Framework-neutral baseline detector training contracts and orchestration."""

from hogflow.training.configuration import TrainingConfiguration, TrainingProfile
from hogflow.training.contracts import DetectorTrainer
from hogflow.training.dataset import load_prepared_training_dataset
from hogflow.training.models import (
    BaselineTrainingResult,
    DetectorTrainingOutput,
    DetectorValidationOutput,
    FailureAnalysisSummary,
    FrameworkMetric,
    PreparedEvaluationDataset,
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
    "PreparedEvaluationDataset",
    "PreparedTrainingDataset",
    "TrainingConfiguration",
    "TrainingProfile",
    "TrainingMetrics",
    "TrainingRunMetadata",
    "ValidationPrediction",
    "load_prepared_training_dataset",
]
