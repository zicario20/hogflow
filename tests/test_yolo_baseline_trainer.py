from pathlib import Path

import pytest
from _phase4_3_helpers import (
    FakeBoxes,
    FakePredictionResult,
    create_prepared_dataset,
    fake_yolo_factory,
)

from hogflow.adapters.yolo_baseline_trainer import YOLOBaselineTrainer
from hogflow.annotation.models import DatasetSplit
from hogflow.core import InputDataError
from hogflow.evaluation import DetectionFrame
from hogflow.training import (
    DetectorTrainingOutput,
    DetectorValidationOutput,
    FrameworkMetric,
    TrainingConfiguration,
)
from hogflow.training.dataset import load_prepared_training_dataset


def _trainer(tmp_path: Path, state: dict[str, object]) -> YOLOBaselineTrainer:
    return YOLOBaselineTrainer(
        "yolo11n.pt",
        tmp_path / "outputs",
        yolo_factory=fake_yolo_factory(state),
        framework_version="synthetic-1",
    )


def _dataset(tmp_path: Path):
    root = tmp_path / "dataset"
    manifest = create_prepared_dataset(root)
    return load_prepared_training_dataset(root, manifest)


def test_train_passes_reproducibility_configuration_and_exports_checkpoint(
    tmp_path: Path,
) -> None:
    state: dict[str, object] = {}
    trainer = _trainer(tmp_path, state)
    configuration = TrainingConfiguration(epochs=3, batch_size=2, seed=7)

    output = trainer.train(_dataset(tmp_path), configuration)

    assert isinstance(output, DetectorTrainingOutput)
    assert output.best_checkpoint_path.read_bytes() == b"synthetic checkpoint"
    assert output.best_checkpoint_path.parent.name == configuration.run_name
    assert output.framework_metrics == (
        FrameworkMetric("fitness", 0.4),
        FrameworkMetric("metrics/mAP50(B)", 0.5),
    )
    arguments = state["train_kwargs"]
    assert arguments["epochs"] == 3
    assert arguments["batch"] == 2
    assert arguments["seed"] == 7
    assert arguments["deterministic"] is True
    assert arguments["workers"] == 0


def test_training_rerun_is_idempotent_for_identical_checkpoint(tmp_path: Path) -> None:
    state: dict[str, object] = {}
    trainer = _trainer(tmp_path, state)
    dataset = _dataset(tmp_path)
    configuration = TrainingConfiguration(epochs=1)

    first = trainer.train(dataset, configuration)
    second = trainer.train(dataset, configuration)

    assert first.best_checkpoint_path == second.best_checkpoint_path


def test_resume_checkpoint_is_passed_explicitly(tmp_path: Path) -> None:
    state: dict[str, object] = {}
    trainer = _trainer(tmp_path, state)
    resume = tmp_path / "resume.pt"
    resume.write_bytes(b"resume")

    trainer.train(
        _dataset(tmp_path),
        TrainingConfiguration(epochs=2),
        resume_checkpoint=resume,
    )

    assert state["train_source"] == str(resume)
    assert state["train_kwargs"]["resume"] == str(resume)


def test_missing_resume_checkpoint_is_rejected(tmp_path: Path) -> None:
    trainer = _trainer(tmp_path, {})

    with pytest.raises(InputDataError, match="Resume checkpoint"):
        trainer.train(
            _dataset(tmp_path),
            TrainingConfiguration(epochs=1),
            resume_checkpoint=tmp_path / "missing.pt",
        )


def test_validate_converts_private_results_to_detection_frames(tmp_path: Path) -> None:
    state: dict[str, object] = {}
    trainer = _trainer(tmp_path, state)
    dataset = _dataset(tmp_path)
    configuration = TrainingConfiguration(epochs=1)
    trained = trainer.train(dataset, configuration)

    result = trainer.validate(dataset, trained.best_checkpoint_path, configuration)

    assert isinstance(result, DetectorValidationOutput)
    assert len(result.frames) == 1
    assert isinstance(result.frames[0], DetectionFrame)
    assert len(result.frames[0].ground_truth) == 1
    assert len(result.frames[0].predictions) == 1
    assert result.frames[0].predictions[0].confidence == 0.9
    assert result.framework_metrics == (
        FrameworkMetric("metrics/mAP50(B)", 0.6),
        FrameworkMetric("metrics/precision(B)", 0.75),
        FrameworkMetric("metrics/recall(B)", 0.5),
    )
    assert not hasattr(result.frames[0], "boxes")


def test_validate_supports_verified_empty_test_split(tmp_path: Path) -> None:
    state: dict[str, object] = {"prediction_results": [FakePredictionResult()]}
    trainer = _trainer(tmp_path, state)
    dataset = _dataset(tmp_path)
    configuration = TrainingConfiguration(
        epochs=1,
        evaluation_split=DatasetSplit.TEST,
    )
    trained = trainer.train(dataset, configuration)

    result = trainer.validate(dataset, trained.best_checkpoint_path, configuration)

    assert result.frames[0].ground_truth == ()
    assert result.frames[0].predictions == ()
    assert state["val_kwargs"]["split"] == "test"


def test_validate_clips_framework_boxes_and_skips_zero_area(tmp_path: Path) -> None:
    state: dict[str, object] = {
        "prediction_results": [
            FakePredictionResult(
                FakeBoxes(
                    xyxy=((-10, -10, 130, 110), (10, 10, 10, 20)),
                    confidence=(0.8, 0.7),
                    classes=(0, 0),
                )
            )
        ]
    }
    trainer = _trainer(tmp_path, state)
    dataset = _dataset(tmp_path)
    configuration = TrainingConfiguration(epochs=1)
    trained = trainer.train(dataset, configuration)

    result = trainer.validate(dataset, trained.best_checkpoint_path, configuration)

    assert len(result.frames[0].predictions) == 1
    box = result.frames[0].predictions[0].bounding_box.bounding_box
    assert (box.x_min, box.y_min, box.x_max, box.y_max) == (0.0, 0.0, 120.0, 100.0)


def test_test_evaluation_requires_test_frames(tmp_path: Path) -> None:
    state: dict[str, object] = {}
    root = tmp_path / "dataset"
    manifest = create_prepared_dataset(root, include_test=False)
    dataset = load_prepared_training_dataset(root, manifest)
    trainer = _trainer(tmp_path, state)
    configuration = TrainingConfiguration(epochs=1, evaluation_split=DatasetSplit.TEST)
    trained = trainer.train(dataset, configuration)

    with pytest.raises(InputDataError, match="no finalized frames"):
        trainer.validate(dataset, trained.best_checkpoint_path, configuration)


def test_adapter_properties_are_sanitized(tmp_path: Path) -> None:
    trainer = YOLOBaselineTrainer(
        str(tmp_path / "private" / "model.pt"),
        tmp_path / "output",
        yolo_factory=fake_yolo_factory({}),
        framework_version="synthetic-1",
    )

    assert trainer.trainer_name == "ultralytics-yolo"
    assert trainer.trainer_version == "synthetic-1"
    assert trainer.model_reference == "model.pt"
    assert str(tmp_path) not in trainer.model_reference

    windows_trainer = YOLOBaselineTrainer(
        r"C:\Users\synthetic-user\private model\baseline.pt",
        tmp_path / "windows-output",
        yolo_factory=fake_yolo_factory({}),
        framework_version="synthetic-1",
    )
    assert windows_trainer.model_reference == "baseline.pt"


def test_real_runtime_configuration_is_redirected_to_local_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import hogflow.adapters.yolo_baseline_trainer as module

    state: dict[str, object] = {}
    monkeypatch.setenv("MPLCONFIGDIR", "outside")
    monkeypatch.setenv("YOLO_CONFIG_DIR", "outside")
    monkeypatch.setattr(
        module,
        "_load_yolo_runtime",
        lambda: (fake_yolo_factory(state), "synthetic-1"),
    )
    output = tmp_path / "local-output"

    module.YOLOBaselineTrainer("yolo11n.pt", output)

    expected_cache = (output / "runs" / ".framework-cache").resolve()
    assert Path(module.os.environ["MPLCONFIGDIR"]) == expected_cache / "matplotlib"
    assert Path(module.os.environ["YOLO_CONFIG_DIR"]) == expected_cache / "yolo"
    assert (expected_cache / "yolo" / "Ultralytics").is_dir()
