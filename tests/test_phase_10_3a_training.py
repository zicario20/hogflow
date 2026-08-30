from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest
from _phase4_3_helpers import create_prepared_dataset, fake_yolo_factory

from hogflow.adapters.yolo_baseline_trainer import YOLOBaselineTrainer
from hogflow.annotation.manifest import write_annotation_manifest
from hogflow.annotation.models import (
    ANNOTATION_POLICY_VERSION,
    AnnotationDatasetManifest,
    AnnotationFrameRecord,
    AnnotationStatus,
    DatasetSplit,
    FrameAnnotation,
    PigAnnotation,
)
from hogflow.annotation.yolo import write_yolo_label
from hogflow.core import ConfigurationError, InputDataError
from hogflow.evaluation import CoordinateSpace, EvaluationBoundingBox
from hogflow.models import BoundingBox
from hogflow.provisional.evaluation import load_prepared_evaluation_dataset
from hogflow.training import TrainingConfiguration, TrainingProfile
from hogflow.training.dataset import load_prepared_training_dataset


def test_demo_profile_fingerprints_every_effective_setting() -> None:
    configuration = TrainingConfiguration.demo_phase_10_3a(
        epochs=75,
        batch_size=4,
        device="cpu",
        seed=17,
        patience=20,
    )
    same = TrainingConfiguration.demo_phase_10_3a(
        epochs=75,
        batch_size=4,
        device="cpu",
        seed=17,
        patience=20,
    )
    different = TrainingConfiguration.demo_phase_10_3a(
        epochs=75,
        batch_size=4,
        device="cpu",
        seed=18,
        patience=20,
    )

    assert configuration.profile is TrainingProfile.PHASE_10_3A_DEMO
    assert configuration.configuration_fingerprint == same.configuration_fingerprint
    assert configuration.configuration_fingerprint != different.configuration_fingerprint
    assert configuration.early_stopping_patience == 20
    assert configuration.augmentation_settings
    assert len(configuration.configuration_fingerprint) == 64


def test_demo_profile_allows_up_to_one_hundred_epochs_but_baseline_cap_remains() -> None:
    assert TrainingConfiguration.demo_phase_10_3a(epochs=100).epochs == 100
    with pytest.raises(ConfigurationError):
        TrainingConfiguration.demo_phase_10_3a(epochs=101)


def test_training_loader_scopes_validation_to_a_manifest_partition(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    manifest_path = create_prepared_dataset(root, include_test=False)
    extra_image = root / "images" / "test" / f"{'d' * 24}.png"
    extra_image.parent.mkdir(parents=True, exist_ok=True)
    extra_image.write_bytes(next((root / "images" / "train").glob("*.png")).read_bytes())

    dataset = load_prepared_training_dataset(root, manifest_path)

    assert dataset.validation_report.valid
    assert dataset.dataset_version
    assert all(frame_id != "d" * 24 for frame_id in dataset.train_frame_ids)


def test_holdout_loader_accepts_validation_only_manifest_without_training_split(
    tmp_path: Path,
) -> None:
    root, manifest_path = _write_evaluation_manifest(tmp_path)

    dataset = load_prepared_evaluation_dataset(root, manifest_path)

    assert dataset.frame_ids == tuple(sorted(dataset.frame_ids))
    assert dataset.frame_ids == ("e" * 24,)
    assert dataset.validation_report.valid
    assert dataset.dataset_version


def test_holdout_loader_rejects_a_training_frame(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    manifest_path = create_prepared_dataset(root)

    with pytest.raises(InputDataError, match="must not contain training"):
        load_prepared_evaluation_dataset(root, manifest_path)


def test_demo_training_passes_patience_and_moderate_augmentation_to_ultralytics(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dataset"
    manifest_path = create_prepared_dataset(root)
    dataset = load_prepared_training_dataset(root, manifest_path)
    state: dict[str, object] = {}
    trainer = YOLOBaselineTrainer(
        "yolo11n.pt",
        tmp_path / "output",
        yolo_factory=fake_yolo_factory(state),
        framework_version="synthetic-1",
    )
    configuration = TrainingConfiguration.demo_phase_10_3a(epochs=75, patience=20)

    trainer.train(dataset, configuration)

    arguments = state["train_kwargs"]
    assert arguments["epochs"] == 75
    assert arguments["patience"] == 20
    for name, value in configuration.augmentation_settings.items():
        assert arguments[name] == value


def test_demo_training_passes_integer_close_mosaic_to_ultralytics(
    tmp_path: Path,
) -> None:
    root = tmp_path / "dataset"
    manifest_path = create_prepared_dataset(root)
    dataset = load_prepared_training_dataset(root, manifest_path)
    state: dict[str, object] = {}
    trainer = YOLOBaselineTrainer(
        "yolo11n.pt",
        tmp_path / "output",
        yolo_factory=fake_yolo_factory(state),
        framework_version="synthetic-1",
    )

    trainer.train(dataset, TrainingConfiguration.demo_phase_10_3a(epochs=1))

    close_mosaic = state["train_kwargs"]["close_mosaic"]
    assert type(close_mosaic) is int
    assert close_mosaic == 10


def test_validate_holdout_predicts_only_evaluation_frames(tmp_path: Path) -> None:
    root, manifest_path = _write_evaluation_manifest(tmp_path)
    dataset = load_prepared_evaluation_dataset(root, manifest_path)
    checkpoint = tmp_path / "checkpoint.pt"
    checkpoint.write_bytes(b"checkpoint")
    state: dict[str, object] = {}
    trainer = YOLOBaselineTrainer(
        "yolo11n.pt",
        tmp_path / "output",
        yolo_factory=fake_yolo_factory(state),
        framework_version="synthetic-1",
    )
    configuration = TrainingConfiguration.demo_phase_10_3a(epochs=1)

    result = trainer.validate_holdout(dataset, checkpoint, configuration)

    assert len(result.frames) == 1
    assert len(state["predict_kwargs"]["source"]) == 1
    assert state["predict_kwargs"]["classes"] == [0]
    assert "val_kwargs" not in state


def _write_evaluation_manifest(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "holdout"
    frame_id = "e" * 24
    clip_id = "f" * 24
    image_relative_path = f"images/test/{frame_id}.png"
    image_path = root / Path(*image_relative_path.split("/"))
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((100, 120, 3), 90, dtype=np.uint8)
    encoded, content = cv2.imencode(".png", image)
    assert encoded
    image_path.write_bytes(content.tobytes())
    record = AnnotationFrameRecord(
        frame_id=frame_id,
        clip_id=clip_id,
        split=DatasetSplit.TEST,
        image_relative_path=image_relative_path,
        width=120,
        height=100,
        annotation_status=AnnotationStatus.ANNOTATED,
        bounding_box_count=1,
        checksum_sha256=hashlib.sha256(image_path.read_bytes()).hexdigest(),
    )
    write_yolo_label(
        FrameAnnotation(
            frame_id,
            AnnotationStatus.ANNOTATED,
            (
                PigAnnotation(
                    EvaluationBoundingBox(
                        BoundingBox(0.2, 0.2, 0.6, 0.6),
                        CoordinateSpace.NORMALIZED,
                    )
                ),
            ),
        ),
        root / "labels" / "test" / f"{frame_id}.txt",
    )
    manifest = AnnotationDatasetManifest(
        schema_version=1,
        dataset_id="phase10-3a-holdout",
        annotation_policy_version=ANNOTATION_POLICY_VERSION,
        class_map=((0, "pig"),),
        frames=(record,),
    )
    manifest_path = root / "metadata" / "dataset_manifest.json"
    write_annotation_manifest(manifest, manifest_path)
    return root, manifest_path
