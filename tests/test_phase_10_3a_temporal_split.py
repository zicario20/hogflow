from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np

from hogflow.annotation.manifest import build_annotation_manifest
from hogflow.annotation.models import (
    ANNOTATION_POLICY_VERSION,
    AnnotationDatasetManifest,
    AnnotationFrameRecord,
    AnnotationSplitPolicy,
    AnnotationStatus,
    DatasetSplit,
    TemporalBlock,
)
from hogflow.annotation.validation import validate_annotation_dataset
from hogflow.annotation.yolo import write_yolo_label

CLIP_ID = "1" * 24
FRAME_A = "a" * 24
FRAME_B = "b" * 24


def test_source_isolated_remains_the_default(tmp_path: Path) -> None:
    manifest = _manifest_with_same_clip_in_train_and_validation(tmp_path)
    report = validate_annotation_dataset(tmp_path, manifest)

    assert "source_video_split_leakage" in {finding.code for finding in report.findings}


def test_temporal_blocks_allow_one_source_only_with_gap_and_timestamps(tmp_path: Path) -> None:
    manifest, root = _temporal_manifest(tmp_path, train_end=4.0, validation_start=5.0)
    report = validate_annotation_dataset(root, manifest)

    assert report.valid


def test_temporal_policy_rejects_overlap_missing_block_or_nonpositive_gap(tmp_path: Path) -> None:
    manifests = (
        _temporal_manifest(tmp_path / "overlap", train_end=4.5, validation_start=4.0),
        _missing_timestamp_manifest(tmp_path / "missing"),
        _temporal_manifest(tmp_path / "zero-gap", train_end=4.0, validation_start=4.0),
    )

    for manifest, root in manifests:
        report = validate_annotation_dataset(root, manifest)
        assert not report.valid


def _manifest_with_same_clip_in_train_and_validation(root: Path) -> AnnotationDatasetManifest:
    first = _record(root, FRAME_A, DatasetSplit.TRAIN, timestamp=1.0, value=30)
    second = _record(root, FRAME_B, DatasetSplit.VALIDATION, timestamp=6.0, value=60)
    return AnnotationDatasetManifest(
        schema_version=1,
        dataset_id="synthetic-temporal",
        annotation_policy_version=ANNOTATION_POLICY_VERSION,
        class_map=((0, "pig"),),
        frames=(first, second),
    )


def _temporal_manifest(
    root: Path, *, train_end: float, validation_start: float
) -> tuple[AnnotationDatasetManifest, Path]:
    first = _record(root, FRAME_A, DatasetSplit.TRAIN, timestamp=1.0, value=30, block_id="block_a")
    second = _record(
        root,
        FRAME_B,
        DatasetSplit.VALIDATION,
        timestamp=max(validation_start, 5.5),
        value=60,
        block_id="block_b",
    )
    _write_labels(root, first, second)
    manifest = AnnotationDatasetManifest(
        schema_version=2,
        dataset_id="synthetic-temporal",
        annotation_policy_version=ANNOTATION_POLICY_VERSION,
        class_map=((0, "pig"),),
        frames=(first, second),
        split_policy=AnnotationSplitPolicy.TEMPORAL_BLOCKED,
        temporal_blocks=(
            TemporalBlock("block_a", CLIP_ID, DatasetSplit.TRAIN, 0.0, train_end),
            TemporalBlock("block_b", CLIP_ID, DatasetSplit.VALIDATION, validation_start, 9.0),
        ),
    )
    return manifest, root


def _missing_timestamp_manifest(root: Path) -> tuple[AnnotationDatasetManifest, Path]:
    first = _record(root, FRAME_A, DatasetSplit.TRAIN, timestamp=None, value=30, block_id="block_a")
    second = _record(root, FRAME_B, DatasetSplit.VALIDATION, timestamp=6.0, value=60, block_id="block_b")
    _write_labels(root, first, second)
    manifest = AnnotationDatasetManifest(
        schema_version=2,
        dataset_id="synthetic-temporal",
        annotation_policy_version=ANNOTATION_POLICY_VERSION,
        class_map=((0, "pig"),),
        frames=(first, second),
        split_policy=AnnotationSplitPolicy.TEMPORAL_BLOCKED,
        temporal_blocks=(
            TemporalBlock("block_a", CLIP_ID, DatasetSplit.TRAIN, 0.0, 4.0),
            TemporalBlock("block_b", CLIP_ID, DatasetSplit.VALIDATION, 5.0, 9.0),
        ),
    )
    return manifest, root


def _record(
    root: Path,
    frame_id: str,
    split: DatasetSplit,
    *,
    timestamp: float | None,
    value: int,
    block_id: str | None = None,
) -> AnnotationFrameRecord:
    relative = f"images/{split.value}/{frame_id}.png"
    image_path = root / Path(*relative.split("/"))
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((24, 32, 3), value, dtype=np.uint8)
    encoded, content = cv2.imencode(".png", image)
    assert encoded
    image_path.write_bytes(content.tobytes())
    return AnnotationFrameRecord(
        frame_id=frame_id,
        clip_id=CLIP_ID,
        split=split,
        image_relative_path=relative,
        width=32,
        height=24,
        annotation_status=AnnotationStatus.VERIFIED_EMPTY,
        bounding_box_count=0,
        checksum_sha256=hashlib.sha256(image_path.read_bytes()).hexdigest(),
        source_timestamp_seconds=timestamp,
        temporal_block_id=block_id,
    )


def _write_labels(root: Path, *records: AnnotationFrameRecord) -> None:
    for record in records:
        label = root / "labels" / record.split.value / f"{record.frame_id}.txt"
        label.parent.mkdir(parents=True, exist_ok=True)
        write_yolo_label(annotation=_frame_annotation(record), path=label)


def _frame_annotation(record: AnnotationFrameRecord):
    from hogflow.annotation.models import FrameAnnotation

    return FrameAnnotation(record.frame_id, record.annotation_status, ())
