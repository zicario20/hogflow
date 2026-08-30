from __future__ import annotations

import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from hogflow.annotation.manifest import prepare_manifest
from hogflow.annotation.models import (
    ANNOTATION_POLICY_VERSION,
    AnnotationDatasetManifest,
    AnnotationFrameRecord,
    AnnotationSplitPolicy,
    AnnotationStatus,
    DatasetSplit,
    TemporalBlock,
)
from hogflow.annotation.validation import build_parser, validate_annotation_dataset
from hogflow.core import InputDataError

CLIP_A = "1" * 24
CLIP_B = "2" * 24
FRAME_A = "a" * 24
FRAME_B = "b" * 24
FRAME_C = "c" * 24


def test_prepare_manifest_can_scope_phase10_3a_blocks(tmp_path: Path) -> None:
    extraction = {
        "records": [
            _extraction_record(FRAME_A, CLIP_A, "train", "train_block_a"),
            _extraction_record(FRAME_B, CLIP_A, "validation", "validation_block_a"),
            _extraction_record(FRAME_C, CLIP_B, "test", "holdout_block_b"),
        ]
    }
    status = {
        "dataset_id": "phase10_3a-demo",
        "frames": {
            frame_id: {"status": "verified_empty", "bounding_box_count": 0}
            for frame_id in (FRAME_A, FRAME_B, FRAME_C)
        },
    }
    frame_plan = {
        "phase10_3a_block_plan": {
            "blocks": [
                _block("train_block_a", CLIP_A, "train", 0.0, 4.0),
                _block("validation_block_a", CLIP_A, "validation", 5.0, 9.0),
                _block("holdout_block_b", CLIP_B, "test", 0.0, 9.0),
            ]
        }
    }
    extraction_path = tmp_path / "extraction.json"
    status_path = tmp_path / "status.json"
    frame_plan_path = tmp_path / "frame-plan.json"
    extraction_path.write_text(json.dumps(extraction), encoding="utf-8")
    status_path.write_text(json.dumps(status), encoding="utf-8")
    frame_plan_path.write_text(json.dumps(frame_plan), encoding="utf-8")

    development = prepare_manifest(
        extraction_report_path=extraction_path,
        status_map_path=status_path,
        frame_plan_path=frame_plan_path,
        temporal_block_ids=("train_block_a", "validation_block_a"),
        output_path=tmp_path / "development.json",
    )
    holdout = prepare_manifest(
        extraction_report_path=extraction_path,
        status_map_path=status_path,
        frame_plan_path=frame_plan_path,
        temporal_block_ids=("holdout_block_b",),
        output_path=tmp_path / "holdout.json",
    )

    assert development.split_policy is AnnotationSplitPolicy.TEMPORAL_BLOCKED
    assert {frame.clip_id for frame in development.frames} == {CLIP_A}
    assert {block.block_id for block in development.temporal_blocks} == {
        "train_block_a",
        "validation_block_a",
    }
    assert holdout.split_policy is AnnotationSplitPolicy.SOURCE_ISOLATED
    assert [frame.frame_id for frame in holdout.frames] == [FRAME_C]
    assert not holdout.temporal_blocks


def test_manifest_scope_validation_ignores_other_explicit_workspace_split(tmp_path: Path) -> None:
    train = _record(tmp_path, FRAME_A, CLIP_A, DatasetSplit.TRAIN, 1.0, "train_block_a")
    validation = _record(
        tmp_path,
        FRAME_B,
        CLIP_A,
        DatasetSplit.VALIDATION,
        6.0,
        "validation_block_a",
    )
    holdout = _record(tmp_path, FRAME_C, CLIP_B, DatasetSplit.TEST, 1.0, "holdout_block_b")
    _write_empty_labels(tmp_path, train, validation, holdout)
    manifest = AnnotationDatasetManifest(
        schema_version=2,
        dataset_id="phase10_3a-demo",
        annotation_policy_version=ANNOTATION_POLICY_VERSION,
        class_map=((0, "pig"),),
        frames=(train, validation),
        split_policy=AnnotationSplitPolicy.TEMPORAL_BLOCKED,
        temporal_blocks=(
            TemporalBlock("train_block_a", CLIP_A, DatasetSplit.TRAIN, 0.0, 4.0),
            TemporalBlock("validation_block_a", CLIP_A, DatasetSplit.VALIDATION, 5.0, 9.0),
        ),
    )

    unscoped = validate_annotation_dataset(tmp_path, manifest)
    scoped = validate_annotation_dataset(tmp_path, manifest, scope_to_manifest=True)

    assert not unscoped.valid
    assert "missing_annotation_status" in {finding.code for finding in unscoped.findings}
    assert scoped.valid
    assert scoped.discovered_image_count == 2
    assert scoped.discovered_label_count == 2


def test_validation_parser_accepts_explicit_manifest_scope() -> None:
    parsed = build_parser().parse_args(
        ["--dataset", "dataset", "--output", "report.json", "--scope-to-manifest"]
    )

    assert parsed.scope_to_manifest is True


def test_prepare_manifest_rejects_unknown_scope_block(tmp_path: Path) -> None:
    extraction_path = tmp_path / "extraction.json"
    status_path = tmp_path / "status.json"
    frame_plan_path = tmp_path / "frame-plan.json"
    extraction_path.write_text(
        json.dumps({"records": [_extraction_record(FRAME_A, CLIP_A, "train", "train_block_a")]}),
        encoding="utf-8",
    )
    status_path.write_text(
        json.dumps(
            {
                "dataset_id": "phase10_3a-demo",
                "frames": {FRAME_A: {"status": "verified_empty", "bounding_box_count": 0}},
            }
        ),
        encoding="utf-8",
    )
    frame_plan_path.write_text(
        json.dumps(
            {
                "phase10_3a_block_plan": {
                    "blocks": [_block("train_block_a", CLIP_A, "train", 0.0, 4.0)]
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(InputDataError, match="unknown temporal block"):
        prepare_manifest(
            extraction_report_path=extraction_path,
            status_map_path=status_path,
            frame_plan_path=frame_plan_path,
            temporal_block_ids=("does_not_exist",),
            output_path=tmp_path / "manifest.json",
        )


def _extraction_record(
    frame_id: str,
    clip_id: str,
    split: str,
    block_id: str,
) -> dict[str, object]:
    return {
        "frame_id": frame_id,
        "clip_id": clip_id,
        "split": split,
        "image_relative_path": f"images/{split}/{frame_id}.png",
        "width": 32,
        "height": 24,
        "checksum_sha256": "f" * 64,
        "actual_timestamp_seconds": 1.0,
        "temporal_block_id": block_id,
    }


def _block(
    block_id: str,
    clip_id: str,
    split: str,
    start_seconds: float,
    end_seconds: float,
) -> dict[str, object]:
    return {
        "block_id": block_id,
        "clip_id": clip_id,
        "split": split,
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
    }


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
    image = np.full((24, 32, 3), int(frame_id[0], 16), dtype=np.uint8)
    encoded, content = cv2.imencode(".png", image)
    assert encoded
    image_path.write_bytes(content.tobytes())
    return AnnotationFrameRecord(
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


def _write_empty_labels(root: Path, *records: AnnotationFrameRecord) -> None:
    for record in records:
        label_path = root / "labels" / record.split.value / f"{record.frame_id}.txt"
        label_path.parent.mkdir(parents=True, exist_ok=True)
        label_path.write_text("", encoding="utf-8")
