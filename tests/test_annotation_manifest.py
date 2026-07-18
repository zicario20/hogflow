import json
from pathlib import Path

import pytest

from hogflow.annotation.manifest import (
    build_annotation_manifest,
    load_annotation_manifest,
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
