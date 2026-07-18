import inspect
from typing import get_type_hints

from hogflow.training import DetectorTrainer


def test_detector_trainer_protocol_is_importable_and_documented() -> None:
    assert inspect.isclass(DetectorTrainer)
    assert inspect.getdoc(DetectorTrainer)
    assert set(DetectorTrainer.__dict__) >= {
        "trainer_name",
        "trainer_version",
        "model_reference",
        "train",
        "validate",
    }


def test_detector_trainer_methods_have_public_type_hints() -> None:
    train_hints = get_type_hints(DetectorTrainer.train)
    validate_hints = get_type_hints(DetectorTrainer.validate)

    assert set(train_hints) == {
        "dataset",
        "configuration",
        "resume_checkpoint",
        "return",
    }
    assert set(validate_hints) == {
        "dataset",
        "checkpoint_path",
        "configuration",
        "return",
    }


def test_detector_trainer_protocol_performs_no_work() -> None:
    assert "ultralytics" not in inspect.getsource(DetectorTrainer).lower()
