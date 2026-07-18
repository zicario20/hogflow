import json
from pathlib import Path

import cv2
import numpy as np

from hogflow.annotation.manifest import build_annotation_manifest, write_annotation_manifest
from hogflow.annotation.models import AnnotationStatus, FrameAnnotation
from hogflow.annotation.validation import validate_annotation_dataset, write_validation_reports
from hogflow.annotation.yolo import write_yolo_label
from hogflow.core import phase4_clip_id
from hogflow.data.dataset_splitting import create_source_split_plan, write_split_plan
from hogflow.data.frame_extraction import ImageFormat, extract_frames, write_extraction_report
from hogflow.data.frame_selection import FrameSelectionSettings, prepare_frame_selection


def _video(path: Path, *, color: int) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        4.0,
        (48, 32),
    )
    assert writer.isOpened()
    for index in range(4):
        frame = np.full((32, 48, 3), color + index, dtype=np.uint8)
        writer.write(frame)
    writer.release()


def test_synthetic_end_to_end_preparation_is_private_and_valid(tmp_path: Path) -> None:
    private_names = (
        "C:/Users/synthetic user/Vídeos/WhatsApp-style one.avi",
        "/home/synthetic user/videos/private two.avi",
        "relative/private review three.avi",
    )
    clip_ids = tuple(phase4_clip_id(name) for name in private_names)
    sources: dict[str, Path] = {}
    for index, clip_id in enumerate(clip_ids):
        source = tmp_path / f"synthetic-source-{index}.avi"
        _video(source, color=30 + index * 50)
        sources[clip_id] = source

    selection_path = tmp_path / "selection.json"
    inventory_path = tmp_path / "inventory.json"
    split_path = tmp_path / "split.json"
    plan_path = tmp_path / "frame-plan.json"
    dataset_root = tmp_path / "annotations"
    selection_path.write_text(
        json.dumps(
            {"decisions": [{"clip_id": clip_id, "status": "selected"} for clip_id in clip_ids]}
        ),
        encoding="utf-8",
    )
    inventory_path.write_text(
        json.dumps(
            {
                "files": [
                    {
                        "relative_path": private_name,
                        "duration_seconds": 1.0,
                        "reviewer_notes": "private review note",
                    }
                    for private_name in private_names
                ]
            }
        ),
        encoding="utf-8",
    )
    split_plan = create_source_split_plan(
        clip_ids,
        seed=123,
        minimum_sources_for_evaluation=3,
    )
    write_split_plan(split_plan, split_path)
    frame_plan = prepare_frame_selection(
        selection_path=selection_path,
        split_plan_path=split_path,
        inventory_path=inventory_path,
        output_path=plan_path,
        settings=FrameSelectionSettings(
            target_frame_count=1,
            maximum_frames_per_clip=1,
            start_exclusion_seconds=0,
            end_exclusion_seconds=0,
        ),
    )
    extraction = extract_frames(
        frame_plan,
        sources,
        dataset_root,
        image_format=ImageFormat.PNG,
    )
    extraction_path = dataset_root / "metadata" / "extraction_report.json"
    write_extraction_report(extraction, extraction_path)
    extraction_payload = json.loads(extraction_path.read_text(encoding="utf-8"))
    status_map = {
        "dataset_id": "synthetic-pilot",
        "frames": {
            record.frame_id: {"status": "verified_empty", "bounding_box_count": 0}
            for record in extraction.records
        },
    }
    manifest = build_annotation_manifest(extraction_payload, status_map)
    manifest_path = dataset_root / "metadata" / "dataset_manifest.json"
    write_annotation_manifest(manifest, manifest_path)
    for record in manifest.frames:
        write_yolo_label(
            FrameAnnotation(record.frame_id, AnnotationStatus.VERIFIED_EMPTY),
            dataset_root / "labels" / record.split.value / f"{record.frame_id}.txt",
        )
    report = validate_annotation_dataset(dataset_root, manifest)
    report_paths = write_validation_reports(
        report,
        tmp_path / "evaluation" / "annotation_validation.json",
    )

    assert report.valid
    assert len(frame_plan.frames) == 3
    assert split_plan.summary.train_clips == 1
    assert split_plan.summary.validation_clips == 1
    assert split_plan.summary.test_clips == 1
    assert {record.split.value for record in extraction.records} == {
        "train",
        "validation",
        "test",
    }
    sanitized_content = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (split_path, plan_path, extraction_path, manifest_path, *report_paths)
    )
    for private_value in (*private_names, str(tmp_path), "private review note"):
        assert private_value not in sanitized_content
