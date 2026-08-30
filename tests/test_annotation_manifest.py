import json
from pathlib import Path

import pytest

from hogflow.annotation.manifest import (
    build_annotation_manifest,
    build_parser,
    load_annotation_manifest,
    prepare_manifest,
    write_annotation_manifest,
)
from hogflow.core import InputDataError

CLIP_ID = "9" * 24
FRAME_ID = "a" * 24
CHECKSUM = "b" * 64


def _extraction_record(
    *,
    frame_id: str = FRAME_ID,
    clip_id: str = CLIP_ID,
    split: str = "preparation",
) -> dict[str, object]:
    return {
        "frame_id": frame_id,
        "clip_id": clip_id,
        "split": split,
        "image_relative_path": f"images/{split}/{frame_id}.png",
        "width": 64,
        "height": 48,
        "checksum_sha256": CHECKSUM,
        "local_source_path": "C:/Users/synthetic/WhatsApp private ü.mp4",
        "reviewer_notes": "private note must never escape",
    }


def test_build_manifest_omits_private_fields_and_is_stable(tmp_path: Path) -> None:
    manifest = build_annotation_manifest(
        {"records": [_extraction_record()]},
        {
            "dataset_id": "synthetic-dataset",
            "frames": {
                FRAME_ID: {"status": "annotated", "bounding_box_count": 2},
            },
        },
    )
    output = tmp_path / "manifest.json"

    write_annotation_manifest(manifest, output)
    first = output.read_text(encoding="utf-8")
    write_annotation_manifest(manifest, output)

    assert output.read_text(encoding="utf-8") == first
    assert load_annotation_manifest(output) == manifest
    assert "C:/Users" not in first
    assert "WhatsApp" not in first
    assert "private note" not in first


def test_manifest_requires_explicit_status_for_every_frame() -> None:
    with pytest.raises(InputDataError, match="missing"):
        build_annotation_manifest(
            {"records": [_extraction_record()]},
            {"dataset_id": "synthetic-dataset", "frames": {}},
        )


def test_manifest_rejects_unknown_or_duplicate_frame_ids() -> None:
    with pytest.raises(InputDataError, match="unknown"):
        build_annotation_manifest(
            {"records": [_extraction_record()]},
            {
                "dataset_id": "synthetic-dataset",
                "frames": {
                    FRAME_ID: {"status": "verified_empty", "bounding_box_count": 0},
                    "c" * 24: {"status": "verified_empty", "bounding_box_count": 0},
                },
            },
        )
    with pytest.raises(InputDataError, match="duplicate"):
        build_annotation_manifest(
            {"records": [_extraction_record(), _extraction_record()]},
            {
                "dataset_id": "synthetic-dataset",
                "frames": {
                    FRAME_ID: {"status": "verified_empty", "bounding_box_count": 0},
                },
            },
        )


def test_manifest_creation_enforces_source_video_split_isolation() -> None:
    second_frame = "d" * 24
    with pytest.raises(InputDataError, match="more than one"):
        build_annotation_manifest(
            {
                "records": [
                    _extraction_record(split="train"),
                    _extraction_record(frame_id=second_frame, split="test"),
                ]
            },
            {
                "dataset_id": "synthetic-dataset",
                "frames": {
                    FRAME_ID: {"status": "verified_empty", "bounding_box_count": 0},
                    second_frame: {"status": "verified_empty", "bounding_box_count": 0},
                },
            },
        )


def test_manifest_json_has_only_expected_sanitized_fields(tmp_path: Path) -> None:
    manifest = build_annotation_manifest(
        {"records": [_extraction_record()]},
        {
            "dataset_id": "synthetic-dataset",
            "frames": {
                FRAME_ID: {"status": "verified_empty", "bounding_box_count": 0},
            },
        },
    )
    output = tmp_path / "manifest.json"
    write_annotation_manifest(manifest, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert set(payload) == {
        "annotation_policy_version",
        "class_map",
        "dataset_id",
        "frames",
        "schema_version",
    }
    assert set(payload["frames"][0]) == {
        "annotation_status",
        "bounding_box_count",
        "checksum_sha256",
        "clip_id",
        "frame_id",
        "height",
        "image_relative_path",
        "split",
        "validation_status",
        "width",
    }


def test_prepare_manifest_uses_explicit_temporal_blocks_from_frame_plan(tmp_path: Path) -> None:
    train_frame_id = FRAME_ID
    validation_frame_id = "d" * 24
    extraction_report = {
        "records": [
            {
                **_extraction_record(frame_id=train_frame_id, split="train"),
                "temporal_block_id": "train_block_a",
            },
            {
                **_extraction_record(frame_id=validation_frame_id, split="validation"),
                "temporal_block_id": "validation_block_a",
            },
        ]
    }
    status_map = {
        "dataset_id": "synthetic-dataset",
        "frames": {
            train_frame_id: {"status": "verified_empty", "bounding_box_count": 0},
            validation_frame_id: {"status": "verified_empty", "bounding_box_count": 0},
        },
    }
    frame_plan = {
        "format_version": 1,
        "frames": [
            {
                "frame_id": train_frame_id,
                "clip_id": CLIP_ID,
                "split": "train",
                "planned_timestamp_seconds": 1.0,
                "selection_strategy": "target_count",
                "temporal_block_id": "train_block_a",
            },
            {
                "frame_id": validation_frame_id,
                "clip_id": CLIP_ID,
                "split": "validation",
                "planned_timestamp_seconds": 9.0,
                "selection_strategy": "target_count",
                "temporal_block_id": "validation_block_a",
            },
        ],
        "phase10_3a_block_plan": {
            "blocks": [
                {
                    "block_id": "train_block_a",
                    "clip_id": CLIP_ID,
                    "split": "train",
                    "start_seconds": 0.0,
                    "end_seconds": 8.0,
                    "video_id": "demo_video_a",
                    "target_frame_count": 48,
                },
                {
                    "block_id": "validation_block_a",
                    "clip_id": CLIP_ID,
                    "split": "validation",
                    "start_seconds": 8.75,
                    "end_seconds": 11.17,
                    "video_id": "demo_video_a",
                    "target_frame_count": 16,
                },
                {
                    "block_id": "holdout_block_b",
                    "clip_id": "c" * 24,
                    "split": "test",
                    "start_seconds": 0.0,
                    "end_seconds": 18.09,
                    "video_id": "demo_video_b",
                    "target_frame_count": 36,
                },
            ],
        },
    }
    extraction_path = tmp_path / "extraction.json"
    status_path = tmp_path / "status.json"
    frame_plan_path = tmp_path / "frame-plan.json"
    output_path = tmp_path / "manifest.json"
    extraction_path.write_text(json.dumps(extraction_report), encoding="utf-8")
    status_path.write_text(json.dumps(status_map), encoding="utf-8")
    frame_plan_path.write_text(json.dumps(frame_plan), encoding="utf-8")

    manifest = prepare_manifest(
        extraction_report_path=extraction_path,
        status_map_path=status_path,
        frame_plan_path=frame_plan_path,
        output_path=output_path,
    )

    assert manifest.split_policy.value == "temporal_blocked"
    assert [block.block_id for block in manifest.temporal_blocks] == [
        "holdout_block_b",
        "train_block_a",
        "validation_block_a",
    ]
    assert [frame.temporal_block_id for frame in manifest.frames] == [
        "train_block_a",
        "validation_block_a",
    ]
    assert load_annotation_manifest(output_path) == manifest


def test_prepare_manifest_defaults_to_source_isolation_without_frame_plan(
    tmp_path: Path,
) -> None:
    extraction_path = tmp_path / "extraction.json"
    status_path = tmp_path / "status.json"
    output_path = tmp_path / "manifest.json"
    extraction_path.write_text(
        json.dumps(
            {
                "records": [
                    _extraction_record(split="train"),
                    _extraction_record(frame_id="d" * 24, split="validation"),
                ]
            }
        ),
        encoding="utf-8",
    )
    status_path.write_text(
        json.dumps(
            {
                "dataset_id": "synthetic-dataset",
                "frames": {
                    FRAME_ID: {"status": "verified_empty", "bounding_box_count": 0},
                    "d" * 24: {"status": "verified_empty", "bounding_box_count": 0},
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(InputDataError, match="more than one dataset split"):
        prepare_manifest(
            extraction_report_path=extraction_path,
            status_map_path=status_path,
            output_path=output_path,
        )


def test_prepare_manifest_rejects_frame_plan_without_explicit_blocks(tmp_path: Path) -> None:
    extraction_path = tmp_path / "extraction.json"
    status_path = tmp_path / "status.json"
    frame_plan_path = tmp_path / "frame-plan.json"
    output_path = tmp_path / "manifest.json"
    extraction_path.write_text(
        json.dumps({"records": [_extraction_record(split="train")]}),
        encoding="utf-8",
    )
    status_path.write_text(
        json.dumps(
            {
                "dataset_id": "synthetic-dataset",
                "frames": {
                    FRAME_ID: {"status": "verified_empty", "bounding_box_count": 0},
                },
            }
        ),
        encoding="utf-8",
    )
    frame_plan_path.write_text(json.dumps({"format_version": 1, "frames": []}), encoding="utf-8")

    with pytest.raises(InputDataError, match="phase10_3a_block_plan.blocks"):
        prepare_manifest(
            extraction_report_path=extraction_path,
            status_map_path=status_path,
            frame_plan_path=frame_plan_path,
            output_path=output_path,
        )


def test_manifest_parser_accepts_optional_frame_plan_argument() -> None:
    parsed = build_parser().parse_args(
        [
            "--extraction-report",
            "extraction.json",
            "--status-map",
            "status.json",
            "--frame-plan",
            "frame-plan.json",
            "--output",
            "manifest.json",
        ]
    )

    assert parsed.frame_plan == Path("frame-plan.json")
