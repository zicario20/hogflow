from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from hogflow.annotation.models import DatasetSplit
from hogflow.core import ConfigurationError, InputDataError
from hogflow.training import FrameworkMetric, TrainingConfiguration


def test_training_configuration_is_immutable_and_reproducible_by_default() -> None:
    configuration = TrainingConfiguration()

    assert configuration.epochs == 25
    assert configuration.device == "cpu"
    assert configuration.workers == 0
    assert configuration.seed == 42
    assert configuration.deterministic
    with pytest.raises(FrozenInstanceError):
        configuration.epochs = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("epochs", 0),
        ("epochs", 31),
        ("batch_size", 0),
        ("image_size", 0),
        ("workers", -1),
        ("seed", -1),
        ("confidence_threshold", 0.0),
        ("iou_threshold", 1.1),
        ("small_object_area_ratio", float("nan")),
        ("run_name", "private/run"),
    ),
)
def test_training_configuration_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ConfigurationError):
        TrainingConfiguration(**{field: value})


def test_training_configuration_rejects_training_as_evaluation_split() -> None:
    with pytest.raises(ConfigurationError, match="validation or test"):
        TrainingConfiguration(evaluation_split=DatasetSplit.TRAIN)


def test_framework_metric_is_immutable_and_finite() -> None:
    metric = FrameworkMetric("metrics/mAP50(B)", 0.5)

    assert metric.value == 0.5
    with pytest.raises(FrozenInstanceError):
        metric.value = 0.7  # type: ignore[misc]
    with pytest.raises(InputDataError):
        FrameworkMetric("bad", float("inf"))


def test_framework_metric_contains_no_path_type() -> None:
    metric = FrameworkMetric("precision", 1.0)

    assert not any(isinstance(value, Path) for value in (metric.name, metric.value))
