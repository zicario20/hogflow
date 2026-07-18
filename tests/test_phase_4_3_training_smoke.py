import json
from pathlib import Path

from _phase4_3_helpers import create_prepared_dataset, fake_yolo_factory

from hogflow.adapters.yolo_baseline_trainer import YOLOBaselineTrainer
from hogflow.training.baseline import run_baseline_training
from hogflow.training.configuration import TrainingConfiguration
from hogflow.training.dataset import load_prepared_training_dataset

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def test_synthetic_phase_4_3_training_pipeline_smoke(tmp_path: Path) -> None:
    dataset_root = tmp_path / "prepared"
    manifest_path = create_prepared_dataset(dataset_root)
    dataset = load_prepared_training_dataset(dataset_root, manifest_path)
    output_root = tmp_path / "local-training"
    state: dict[str, object] = {}
    trainer = YOLOBaselineTrainer(
        "synthetic-yolo.pt",
        output_root,
        yolo_factory=fake_yolo_factory(state),
        framework_version="synthetic-1",
    )

    result = run_baseline_training(
        trainer,
        dataset,
        TrainingConfiguration(epochs=1, batch_size=1, image_size=64),
        output_root=output_root,
        repository_root=REPOSITORY_ROOT,
    )

    assert result.training.best_checkpoint_path.is_file()
    assert result.metrics.hogflow.f1_score == 1.0
    assert state["train_kwargs"]["epochs"] == 1
    assert state["predict_kwargs"]["save"] is False
    for path in (
        result.metadata_path,
        result.metrics_path,
        result.failure_report_path,
    ):
        assert path.is_file()
    serialized = result.metadata_path.read_text(encoding="utf-8") + json.dumps(
        json.loads(result.metrics_path.read_text(encoding="utf-8")),
        sort_keys=True,
    )
    assert str(tmp_path) not in serialized
    assert "source_map" not in serialized
