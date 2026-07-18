import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from hogflow.annotation.models import (
    ANNOTATION_POLICY_VERSION,
    AnnotationDatasetManifest,
    AnnotationFrameRecord,
    AnnotationStatus,
    DatasetSplit,
    PigAnnotation,
)
from hogflow.annotation.validation import validate_annotation_dataset, write_validation_reports
from hogflow.annotation.yolo import write_yolo_label
from hogflow.evaluation import CoordinateSpace, EvaluationBoundingBox
from hogflow.models import BoundingBox

CLIP_A = "4" * 24
CLIP_B = "5" * 24
FRAME_A = "6" * 24
FRAME_B = "7" * 24


def _write_image(path: Path, *, value: int = 80) -> tuple[int, int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((24, 32, 3), value, dtype=np.uint8)
    encoded, content_array = cv2.imencode(path.suffix, image)
    assert encoded
    path.write_bytes(content_array.tobytes())
    content = path.read_bytes()
    return 32, 24, hashlib.sha256(content).hexdigest()


def _pig() -> PigAnnotation:
    return PigAnnotation(
        EvaluationBoundingBox(
            BoundingBox(0.1, 0.1, 0.8, 0.8),
            CoordinateSpace.NORMALIZED,
        )
    )


def _record(
    root: Path,
    *,
    frame_id: str,
    clip_id: str,
    split: DatasetSplit,
    status: AnnotationStatus,
    value: int,
    box_count: int,
) -> AnnotationFrameRecord:
    relative = f"images/{split.value}/{frame_id}.png"
    width, height, checksum = _write_image(root / Path(*relative.split("/")), value=value)
    return AnnotationFrameRecord(
        frame_id=frame_id,
        clip_id=clip_id,
        split=split,
        image_relative_path=relative,
        width=width,
        height=height,
        annotation_status=status,
        bounding_box_count=box_count,
        checksum_sha256=checksum,
    )


def _manifest(records: tuple[AnnotationFrameRecord, ...]) -> AnnotationDatasetManifest:
    return AnnotationDatasetManifest(
        schema_version=1,
        dataset_id="synthetic-dataset",
        annotation_policy_version=ANNOTATION_POLICY_VERSION,
        class_map=((0, "pig"),),
        frames=tuple(sorted(records, key=lambda record: record.frame_id)),
    )


def test_valid_annotated_and_verified_empty_frames_pass(tmp_path: Path) -> None:
    annotated = _record(
        tmp_path,
        frame_id=FRAME_A,
        clip_id=CLIP_A,
        split=DatasetSplit.TRAIN,
        status=AnnotationStatus.ANNOTATED,
        value=50,
        box_count=1,
    )
    empty = _record(
        tmp_path,
        frame_id=FRAME_B,
        clip_id=CLIP_B,
        split=DatasetSplit.VALIDATION,
        status=AnnotationStatus.VERIFIED_EMPTY,
        value=100,
        box_count=0,
    )
    write_yolo_label(
        annotation=_frame_annotation(annotated),
        path=tmp_path / "labels" / "train" / f"{FRAME_A}.txt",
    )
    write_yolo_label(
        annotation=_frame_annotation(empty),
        path=tmp_path / "labels" / "validation" / f"{FRAME_B}.txt",
    )

    report = validate_annotation_dataset(tmp_path, _manifest((annotated, empty)))

    assert report.valid
    assert report.error_count == 0
    assert report.discovered_image_count == 2
    assert report.discovered_label_count == 2


def test_empty_label_requires_verified_empty_status(tmp_path: Path) -> None:
    record = _record(
        tmp_path,
        frame_id=FRAME_A,
        clip_id=CLIP_A,
        split=DatasetSplit.TRAIN,
        status=AnnotationStatus.ANNOTATED,
        value=10,
        box_count=1,
    )
    label = tmp_path / "labels" / "train" / f"{FRAME_A}.txt"
    label.parent.mkdir(parents=True, exist_ok=True)
    label.write_text("", encoding="utf-8")

    report = validate_annotation_dataset(tmp_path, _manifest((record,)))

    assert "invalid_yolo_label" in {finding.code for finding in report.findings}
    assert not report.valid


def test_invalid_coordinates_or_orphan_labels_are_errors(tmp_path: Path) -> None:
    record = _record(
        tmp_path,
        frame_id=FRAME_A,
        clip_id=CLIP_A,
        split=DatasetSplit.TRAIN,
        status=AnnotationStatus.ANNOTATED,
        value=10,
        box_count=1,
    )
    label_root = tmp_path / "labels" / "train"
    label_root.mkdir(parents=True, exist_ok=True)
    (label_root / f"{FRAME_A}.txt").write_text("0 0.95 0.5 0.2 0.2\n", encoding="utf-8")
    orphan_id = "8" * 24
    (label_root / f"{orphan_id}.txt").write_text("", encoding="utf-8")

    report = validate_annotation_dataset(tmp_path, _manifest((record,)))
    codes = {finding.code for finding in report.findings}

    assert "invalid_yolo_label" in codes
    assert "orphan_label" in codes


def test_missing_status_and_private_filename_do_not_leak_to_report(tmp_path: Path) -> None:
    private_name = "WhatsApp private user ü image.jpg"
    _write_image(tmp_path / "images" / "train" / private_name)
    (tmp_path / "labels").mkdir(parents=True)

    report = validate_annotation_dataset(tmp_path, _manifest(()))
    serialized = json.dumps(
        [
            finding.__dict__ if hasattr(finding, "__dict__") else finding.message
            for finding in report.findings
        ]
    )

    assert "missing_annotation_status" in {finding.code for finding in report.findings}
    assert private_name not in serialized
    assert str(tmp_path) not in serialized


def test_source_split_leakage_and_cross_split_duplicate_content_are_fatal(
    tmp_path: Path,
) -> None:
    first = _record(
        tmp_path,
        frame_id=FRAME_A,
        clip_id=CLIP_A,
        split=DatasetSplit.TRAIN,
        status=AnnotationStatus.VERIFIED_EMPTY,
        value=20,
        box_count=0,
    )
    second = _record(
        tmp_path,
        frame_id=FRAME_B,
        clip_id=CLIP_A,
        split=DatasetSplit.TEST,
        status=AnnotationStatus.VERIFIED_EMPTY,
        value=20,
        box_count=0,
    )
    for record in (first, second):
        label = tmp_path / "labels" / record.split.value / f"{record.frame_id}.txt"
        label.parent.mkdir(parents=True, exist_ok=True)
        label.write_text("", encoding="utf-8")

    report = validate_annotation_dataset(tmp_path, _manifest((first, second)))
    codes = {finding.code for finding in report.findings}

    assert "source_video_split_leakage" in codes
    assert "duplicate_content_across_splits" in codes
    assert not report.valid


def test_validation_reports_are_deterministic_json_csv_and_markdown(tmp_path: Path) -> None:
    (tmp_path / "images").mkdir()
    (tmp_path / "labels").mkdir()
    report = validate_annotation_dataset(tmp_path, _manifest(()))
    output = tmp_path / "reports" / "validation.json"

    paths = write_validation_reports(report, output)
    first = tuple(path.read_text(encoding="utf-8") for path in paths)
    write_validation_reports(report, output)

    assert tuple(path.suffix for path in paths) == (".json", ".csv", ".md")
    assert tuple(path.read_text(encoding="utf-8") for path in paths) == first
    assert str(tmp_path) not in "".join(first)


def test_unreadable_image_and_unexpected_nested_file_are_reported(tmp_path: Path) -> None:
    image_relative = f"images/train/{FRAME_A}.png"
    image_path = tmp_path / Path(*image_relative.split("/"))
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"not an image")
    unexpected = tmp_path / "images" / "train" / "private annotation tool.bin"
    unexpected.write_bytes(b"local tool state")
    (tmp_path / "labels").mkdir()
    record = AnnotationFrameRecord(
        frame_id=FRAME_A,
        clip_id=CLIP_A,
        split=DatasetSplit.TRAIN,
        image_relative_path=image_relative,
        width=32,
        height=24,
        annotation_status=AnnotationStatus.NEEDS_MANUAL_REVIEW,
        bounding_box_count=0,
        checksum_sha256=hashlib.sha256(image_path.read_bytes()).hexdigest(),
    )

    report = validate_annotation_dataset(tmp_path, _manifest((record,)))
    serialized = json.dumps(
        [
            {
                "code": finding.code,
                "message": finding.message,
                "relative_path": finding.relative_path,
            }
            for finding in report.findings
        ]
    )
    codes = {finding.code for finding in report.findings}

    assert "unreadable_image" in codes
    assert "unexpected_image_file" in codes
    assert unexpected.name not in serialized


def _frame_annotation(record: AnnotationFrameRecord):
    from hogflow.annotation.models import FrameAnnotation

    boxes = (_pig(),) if record.annotation_status is AnnotationStatus.ANNOTATED else ()
    return FrameAnnotation(record.frame_id, record.annotation_status, boxes)
