from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np

from hogflow.annotation.manifest import load_annotation_manifest, write_annotation_manifest
from hogflow.annotation.models import (
    ANNOTATION_POLICY_VERSION,
    AnnotationDatasetManifest,
    AnnotationFrameRecord,
    AnnotationSplitPolicy,
    AnnotationStatus,
    DatasetSplit,
    FrameAnnotation,
    TemporalBlock,
)
from hogflow.annotation.validation import validate_annotation_dataset
from hogflow.annotation.yolo import write_yolo_label


def test_multi_source_temporal_policy_accepts_explicit_blocks(tmp_path: Path) -> None:
    first_train = _record(tmp_path, "a" * 24, "1" * 24, DatasetSplit.TRAIN, 1.0, "a_train")
    first_validation = _record(
        tmp_path, "b" * 24, "1" * 24, DatasetSplit.VALIDATION, 4.0, "a_validation"
    )
    second_train = _record(tmp_path, "c" * 24, "2" * 24, DatasetSplit.TRAIN, 1.0, "b_train")
    second_validation = _record(
        tmp_path, "d" * 24, "2" * 24, DatasetSplit.VALIDATION, 4.0, "b_validation"
    )
    records = (first_train, first_validation, second_train, second_validation)
    manifest = AnnotationDatasetManifest(
        schema_version=2,
        dataset_id="phase10-3b-development",
        annotation_policy_version=ANNOTATION_POLICY_VERSION,
        class_map=((0, "pig"),),
        frames=tuple(sorted(records, key=lambda item: item.frame_id)),
        split_policy=AnnotationSplitPolicy.MULTI_SOURCE_TEMPORAL_BLOCKED,
        temporal_blocks=(
            TemporalBlock("a_train", "1" * 24, DatasetSplit.TRAIN, 0.0, 2.0),
            TemporalBlock("a_validation", "1" * 24, DatasetSplit.VALIDATION, 3.0, 5.0),
            TemporalBlock("b_train", "2" * 24, DatasetSplit.TRAIN, 0.0, 2.0),
            TemporalBlock("b_validation", "2" * 24, DatasetSplit.VALIDATION, 3.0, 5.0),
        ),
    )

    report = validate_annotation_dataset(tmp_path, manifest)

    assert report.valid


def test_multi_source_policy_round_trips_without_weakening_single_source_policy(
    tmp_path: Path,
) -> None:
    records = (
        _record(tmp_path, "e" * 24, "3" * 24, DatasetSplit.TRAIN, 1.0, "source_a_train"),
        _record(tmp_path, "f" * 24, "4" * 24, DatasetSplit.TRAIN, 1.0, "source_b_train"),
    )
    manifest = AnnotationDatasetManifest(
        schema_version=2,
        dataset_id="phase10-3b-roundtrip",
        annotation_policy_version=ANNOTATION_POLICY_VERSION,
        class_map=((0, "pig"),),
        frames=tuple(sorted(records, key=lambda item: item.frame_id)),
        split_policy=AnnotationSplitPolicy.MULTI_SOURCE_TEMPORAL_BLOCKED,
        temporal_blocks=(
            TemporalBlock("source_a_train", "3" * 24, DatasetSplit.TRAIN, 0.0, 2.0),
            TemporalBlock("source_b_train", "4" * 24, DatasetSplit.TRAIN, 0.0, 2.0),
        ),
    )
    path = tmp_path / "metadata" / "dataset_manifest.json"
    write_annotation_manifest(manifest, path)

    loaded = load_annotation_manifest(path)

    assert loaded.split_policy is AnnotationSplitPolicy.MULTI_SOURCE_TEMPORAL_BLOCKED
    assert loaded.temporal_blocks == manifest.temporal_blocks


def _record(
    root: Path,
    frame_id: str,
    clip_id: str,
    split: DatasetSplit,
    timestamp: float,
    block_id: str,
) -> AnnotationFrameRecord:
    relative = f"images/{split.value}/{frame_id}.png"
    image_path = root / Path(*relative.split("/"))
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((24, 32, 3), 30 + (ord(frame_id[0]) - ord("a")), dtype=np.uint8)
    encoded, content = cv2.imencode(".png", image)
    assert encoded
    image_path.write_bytes(content.tobytes())
    record = AnnotationFrameRecord(
        frame_id=frame_id,
        clip_id=clip_id,
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
    label = root / "labels" / split.value / f"{frame_id}.txt"
    write_yolo_label(FrameAnnotation(frame_id, AnnotationStatus.VERIFIED_EMPTY, ()), label)
    return record
