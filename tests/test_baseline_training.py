import json
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
from hogflow.training.baseline import collect_code_provenance, run_baseline_training
from hogflow.training.configuration import TrainingConfiguration
from hogflow.training.dataset import load_prepared_training_dataset

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _run(
    tmp_path: Path,
    *,
    state: dict[str, object] | None = None,
    configuration: TrainingConfiguration | None = None,
):
    dataset_root = tmp_path / "dataset"
    manifest = create_prepared_dataset(dataset_root)
    dataset = load_prepared_training_dataset(dataset_root, manifest)
    output_root = tmp_path / "local-output"
    trainer = YOLOBaselineTrainer(
        "yolo11n.pt",
        output_root,
        yolo_factory=fake_yolo_factory(state or {}),
        framework_version="synthetic-1",
    )
    result = run_baseline_training(
        trainer,
        dataset,
        configuration or TrainingConfiguration(epochs=1),
        output_root=output_root,
        repository_root=REPOSITORY_ROOT,
    )
    return result, output_root


def test_baseline_reuses_hogflow_evaluation_and_writes_local_reports(
    tmp_path: Path,
) -> None:
    result, output_root = _run(
        tmp_path,
        configuration=TrainingConfiguration(epochs=1, small_object_area_ratio=0.2),
    )

    assert result.metrics.hogflow.true_positives == 1
    assert result.metrics.hogflow.false_positives == 0
    assert result.metrics.hogflow.false_negatives == 0
    assert result.metrics.hogflow.precision == 1.0
    assert result.metrics.hogflow.recall == 1.0
    assert result.metrics.hogflow.f1_score == 1.0
    assert result.metrics.mean_matched_iou == pytest.approx(1.0)
    assert result.failure_analysis.very_small_ground_truth_count == 1
    assert result.metadata_path.is_file()
    assert result.metrics_path.is_file()
    assert result.failure_report_path.is_file()
    assert result.training.best_checkpoint_path.is_relative_to(output_root)


def test_framework_and_hogflow_metrics_are_explicitly_separate(tmp_path: Path) -> None:
    result, _output_root = _run(tmp_path)
    payload = json.loads(result.metrics_path.read_text(encoding="utf-8"))

    assert "metrics/mAP50(B)" in payload["framework_training_metrics"]
    assert "metrics/mAP50(B)" in payload["framework_validation_metrics"]
    assert "mAP" not in payload["hogflow_metrics"]
    assert payload["hogflow_metrics"]["precision"] == 1.0
    assert "metric_boundary" in payload


def test_training_metadata_records_reproducibility_without_absolute_paths(
    tmp_path: Path,
) -> None:
    result, _output_root = _run(tmp_path)
    content = result.metadata_path.read_text(encoding="utf-8")
    payload = json.loads(content)

    assert payload["configuration"]["seed"] == 42
    assert payload["dataset_version"]
    assert len(payload["git_commit"]) == 40
    assert payload["code_version"] == "0.1.0"
    assert payload["model_reference"] == "yolo11n.pt"
    assert not Path(payload["best_checkpoint_relative_path"]).is_absolute()
    assert str(tmp_path) not in content


def test_empty_frame_false_positive_is_summarized(tmp_path: Path) -> None:
    state: dict[str, object] = {
        "prediction_results": [
            FakePredictionResult(
                FakeBoxes(
                    xyxy=((10, 10, 40, 40),),
                    confidence=(0.8,),
                    classes=(0,),
                )
            )
        ]
    }
    result, _output_root = _run(
        tmp_path,
        state=state,
        configuration=TrainingConfiguration(
            epochs=1,
            evaluation_split=DatasetSplit.TEST,
        ),
    )

    assert result.metrics.hogflow.false_positives == 1
    assert result.failure_analysis.empty_frame_count == 1
    assert result.failure_analysis.empty_frame_false_positive_count == 1
    report = result.failure_report_path.read_text(encoding="utf-8")
    assert "Heavy occlusions: Unavailable" in report
    assert "counting accuracy" in report


def test_collect_code_provenance_returns_version_and_commit() -> None:
    code_version, commit = collect_code_provenance(REPOSITORY_ROOT)

    assert code_version == "0.1.0"
    assert len(commit) == 40
    assert all(character in "0123456789abcdef" for character in commit)
