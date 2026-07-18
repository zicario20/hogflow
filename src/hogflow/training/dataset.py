"""Local prepared-dataset loading and mandatory pre-training validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from hogflow.annotation.manifest import load_annotation_manifest, manifest_to_dict
from hogflow.annotation.models import (
    AnnotationFrameRecord,
    AnnotationStatus,
    DatasetSplit,
    ManifestValidationStatus,
)
from hogflow.annotation.validation import validate_annotation_dataset
from hogflow.annotation.yolo import parse_yolo
from hogflow.core import InputDataError
from hogflow.evaluation import (
    CoordinateSpace,
    DetectionFrame,
    EvaluationBoundingBox,
    GroundTruthDetection,
    PredictedDetection,
)
from hogflow.models import BoundingBox
from hogflow.training.models import PreparedTrainingDataset, ValidationPrediction

_FINALIZED_STATUSES = frozenset({AnnotationStatus.ANNOTATED, AnnotationStatus.VERIFIED_EMPTY})
_ACTIVE_SPLITS = frozenset({DatasetSplit.TRAIN, DatasetSplit.VALIDATION, DatasetSplit.TEST})


def load_prepared_training_dataset(
    dataset_root: str | Path,
    manifest_path: str | Path,
) -> PreparedTrainingDataset:
    """Load and structurally validate a local YOLO dataset before training.

    This gate reuses Phase 4.2 annotation validation, including source-level
    split isolation, image readability, label parsing, class-map validation,
    dimensions, checksums, and explicit empty-frame state. Any fatal finding
    aborts before a trainer is called.
    """

    root = Path(dataset_root)
    local_manifest_path = Path(manifest_path)
    manifest = load_annotation_manifest(local_manifest_path)
    report = validate_annotation_dataset(root, manifest)
    if not report.valid:
        raise InputDataError(
            f"Prepared dataset validation failed with {report.error_count} fatal issue(s)."
        )

    active_records = tuple(frame for frame in manifest.frames if frame.split in _ACTIVE_SPLITS)
    unready = tuple(
        frame
        for frame in active_records
        if frame.annotation_status not in _FINALIZED_STATUSES
        or frame.validation_status is ManifestValidationStatus.INVALID
    )
    if unready:
        raise InputDataError(
            "Train, validation, and test splits may contain only annotated or "
            "verified-empty frames that are not marked invalid."
        )

    by_split = {
        split: tuple(sorted(frame.frame_id for frame in active_records if frame.split is split))
        for split in (DatasetSplit.TRAIN, DatasetSplit.VALIDATION, DatasetSplit.TEST)
    }
    if not by_split[DatasetSplit.TRAIN] or not by_split[DatasetSplit.VALIDATION]:
        raise InputDataError(
            "Baseline training requires non-empty source-isolated train and validation splits."
        )

    return PreparedTrainingDataset(
        root=root,
        manifest_path=local_manifest_path,
        manifest=manifest,
        validation_report=report,
        dataset_version=_dataset_version(root, manifest.frames, manifest_to_dict(manifest)),
        train_frame_ids=by_split[DatasetSplit.TRAIN],
        validation_frame_ids=by_split[DatasetSplit.VALIDATION],
        test_frame_ids=by_split[DatasetSplit.TEST],
    )


def image_path_for_frame(
    dataset: PreparedTrainingDataset,
    frame_id: str,
) -> Path:
    """Resolve one opaque manifest frame to its local prepared image."""

    record = frame_record(dataset, frame_id)
    return dataset.root / Path(*record.image_relative_path.split("/"))


def label_path_for_frame(
    dataset: PreparedTrainingDataset,
    frame_id: str,
) -> Path:
    """Resolve one opaque manifest frame to its validated local YOLO label."""

    record = frame_record(dataset, frame_id)
    return dataset.root / "labels" / record.split.value / f"{record.frame_id}.txt"


def frame_record(
    dataset: PreparedTrainingDataset,
    frame_id: str,
) -> AnnotationFrameRecord:
    """Return one manifest frame by opaque identifier."""

    if not isinstance(dataset, PreparedTrainingDataset):
        raise InputDataError("dataset must be PreparedTrainingDataset.")
    for record in dataset.manifest.frames:
        if record.frame_id == frame_id:
            return record
    raise InputDataError("Opaque frame ID is not present in the prepared dataset.")


def build_detection_frame(
    dataset: PreparedTrainingDataset,
    frame_id: str,
    predictions: tuple[ValidationPrediction, ...],
) -> DetectionFrame:
    """Combine validated YOLO ground truth with framework-neutral predictions."""

    if not isinstance(predictions, tuple) or not all(
        isinstance(item, ValidationPrediction) for item in predictions
    ):
        raise InputDataError("predictions must be an immutable ValidationPrediction tuple.")
    record = frame_record(dataset, frame_id)
    try:
        label_text = label_path_for_frame(dataset, record.frame_id).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise InputDataError(
            f"Validated YOLO label is unavailable for opaque frame {record.frame_id!r}."
        ) from exc
    annotation = parse_yolo(
        label_text,
        frame_id=record.frame_id,
        status=record.annotation_status,
    )
    ground_truth = tuple(
        GroundTruthDetection(
            detection_id=f"gt-{index:06d}",
            bounding_box=_pixel_evaluation_box(
                BoundingBox(
                    pig.bounding_box.bounding_box.x_min * record.width,
                    pig.bounding_box.bounding_box.y_min * record.height,
                    pig.bounding_box.bounding_box.x_max * record.width,
                    pig.bounding_box.bounding_box.y_max * record.height,
                )
            ),
        )
        for index, pig in enumerate(annotation.boxes)
    )
    predicted = tuple(
        PredictedDetection(
            detection_id=f"pred-{index:06d}",
            bounding_box=_pixel_evaluation_box(prediction.bounding_box),
            confidence=prediction.confidence,
            class_name=prediction.class_name,
        )
        for index, prediction in enumerate(predictions)
    )
    return DetectionFrame(
        source_video_id=record.clip_id,
        frame_id=record.frame_id,
        width=record.width,
        height=record.height,
        ground_truth=ground_truth,
        predictions=predicted,
    )


def _pixel_evaluation_box(box: BoundingBox) -> EvaluationBoundingBox:
    return EvaluationBoundingBox(box, CoordinateSpace.PIXEL)


def _dataset_version(
    root: Path,
    frames: tuple[AnnotationFrameRecord, ...],
    manifest_payload: dict[str, object],
) -> str:
    digest = hashlib.sha256()
    digest.update(
        json.dumps(
            manifest_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    )
    for frame in frames:
        if frame.split not in _ACTIVE_SPLITS or frame.annotation_status not in _FINALIZED_STATUSES:
            continue
        label_path = root / "labels" / frame.split.value / f"{frame.frame_id}.txt"
        try:
            label_content = label_path.read_bytes()
        except OSError as exc:
            raise InputDataError(
                f"Validated label bytes are unavailable for opaque frame {frame.frame_id!r}."
            ) from exc
        digest.update(frame.frame_id.encode("ascii"))
        digest.update(label_content)
    return digest.hexdigest()


__all__ = [
    "frame_record",
    "build_detection_frame",
    "image_path_for_frame",
    "label_path_for_frame",
    "load_prepared_training_dataset",
]
