from pathlib import Path

import pytest
from _phase4_3_helpers import create_prepared_dataset

from hogflow.annotation.manifest import load_annotation_manifest, write_annotation_manifest
from hogflow.annotation.models import AnnotationStatus, DatasetSplit
from hogflow.core import InputDataError
from hogflow.training.dataset import load_prepared_training_dataset


def test_load_prepared_dataset_validates_and_fingerprints_deterministically(
    tmp_path: Path,
) -> None:
    root = tmp_path / "prepared"
    manifest_path = create_prepared_dataset(root)

    first = load_prepared_training_dataset(root, manifest_path)
    second = load_prepared_training_dataset(root, manifest_path)

    assert first.dataset_version == second.dataset_version
    assert len(first.dataset_version) == 64
    assert first.validation_report.valid
    assert len(first.train_frame_ids) == 1
    assert len(first.validation_frame_ids) == 1
    assert len(first.test_frame_ids) == 1


def test_label_change_changes_dataset_version(tmp_path: Path) -> None:
    root = tmp_path / "prepared"
    manifest_path = create_prepared_dataset(root)
    first = load_prepared_training_dataset(root, manifest_path)
    label = next((root / "labels" / "train").glob("*.txt"))
    label.write_text("0 0.4 0.4 0.2 0.2\n", encoding="utf-8")

    second = load_prepared_training_dataset(root, manifest_path)

    assert first.dataset_version != second.dataset_version


def test_invalid_annotation_aborts_before_training(tmp_path: Path) -> None:
    root = tmp_path / "prepared"
    manifest_path = create_prepared_dataset(root)
    label = next((root / "labels" / "validation").glob("*.txt"))
    label.write_text("0 nan 0.5 0.2 0.2\n", encoding="utf-8")

    with pytest.raises(InputDataError, match="validation failed"):
        load_prepared_training_dataset(root, manifest_path)


def test_unready_frame_in_active_split_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "prepared"
    manifest_path = create_prepared_dataset(
        root,
        validation_status=AnnotationStatus.NEEDS_MANUAL_REVIEW,
    )

    with pytest.raises(InputDataError, match="only annotated or verified-empty"):
        load_prepared_training_dataset(root, manifest_path)


def test_missing_validation_split_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "prepared"
    manifest_path = create_prepared_dataset(root)
    manifest = load_annotation_manifest(manifest_path)
    altered = type(manifest)(
        schema_version=manifest.schema_version,
        dataset_id=manifest.dataset_id,
        annotation_policy_version=manifest.annotation_policy_version,
        class_map=manifest.class_map,
        frames=tuple(
            frame for frame in manifest.frames if frame.split is not DatasetSplit.VALIDATION
        ),
    )
    validation_record = next(
        frame for frame in manifest.frames if frame.split is DatasetSplit.VALIDATION
    )
    image = root / Path(*validation_record.image_relative_path.split("/"))
    image.unlink()
    label = root / "labels" / "validation" / f"{validation_record.frame_id}.txt"
    label.unlink()
    write_annotation_manifest(altered, manifest_path)

    with pytest.raises(InputDataError, match="non-empty"):
        load_prepared_training_dataset(root, manifest_path)


def test_unreadable_image_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "prepared"
    manifest_path = create_prepared_dataset(root)
    image = next((root / "images" / "train").glob("*.png"))
    image.write_bytes(b"not an image")

    with pytest.raises(InputDataError, match="validation failed"):
        load_prepared_training_dataset(root, manifest_path)
