from dataclasses import FrozenInstanceError

import pytest

from hogflow.annotation.manifest import manifest_to_dict
from hogflow.annotation.models import (
    ANNOTATION_POLICY_VERSION,
    AnnotationDatasetManifest,
    AnnotationFrameRecord,
    AnnotationStatus,
    DatasetSplit,
    FrameAnnotation,
    ManifestValidationStatus,
    PigAnnotation,
)
from hogflow.annotation.policy import normalized_pig_box_from_pixels
from hogflow.core import InputDataError
from hogflow.evaluation import CoordinateSpace, EvaluationBoundingBox
from hogflow.models import BoundingBox

CLIP_ID = "a" * 24
FRAME_ID = "b" * 24
CHECKSUM = "c" * 64


def _pig_box() -> PigAnnotation:
    return PigAnnotation(
        EvaluationBoundingBox(
            BoundingBox(0.1, 0.2, 0.6, 0.8),
            CoordinateSpace.NORMALIZED,
        )
    )


def test_annotation_models_are_immutable_and_slotted() -> None:
    annotation = FrameAnnotation(
        frame_id=FRAME_ID,
        status=AnnotationStatus.ANNOTATED,
        boxes=(_pig_box(),),
    )

    with pytest.raises(FrozenInstanceError):
        annotation.status = AnnotationStatus.EXCLUDED  # type: ignore[misc]

    assert not hasattr(annotation, "__dict__")


def test_pig_annotation_rejects_invalid_class_and_pixel_coordinates() -> None:
    normalized = EvaluationBoundingBox(
        BoundingBox(0.1, 0.1, 0.5, 0.5),
        CoordinateSpace.NORMALIZED,
    )
    with pytest.raises(InputDataError, match="class ID 0"):
        PigAnnotation(normalized, class_id=1)
    with pytest.raises(InputDataError, match="normalized"):
        PigAnnotation(EvaluationBoundingBox(BoundingBox(1, 1, 5, 5), CoordinateSpace.PIXEL))


def test_boundary_policy_clips_visible_partial_pig_to_image() -> None:
    annotation = normalized_pig_box_from_pixels(
        x_min=-10,
        y_min=20,
        x_max=50,
        y_max=120,
        image_width=100,
        image_height=100,
    )
    box = annotation.bounding_box.bounding_box

    assert box == BoundingBox(0.0, 0.2, 0.5, 1.0)


def test_boundary_policy_rejects_box_with_no_visible_area() -> None:
    with pytest.raises(InputDataError, match="positive"):
        normalized_pig_box_from_pixels(
            x_min=-20,
            y_min=0,
            x_max=-10,
            y_max=20,
            image_width=100,
            image_height=100,
        )


def test_frame_annotation_requires_explicit_consistent_status() -> None:
    with pytest.raises(InputDataError, match="at least one"):
        FrameAnnotation(frame_id=FRAME_ID, status=AnnotationStatus.ANNOTATED)
    with pytest.raises(InputDataError, match="Only frames"):
        FrameAnnotation(
            frame_id=FRAME_ID,
            status=AnnotationStatus.VERIFIED_EMPTY,
            boxes=(_pig_box(),),
        )
    empty = FrameAnnotation(frame_id=FRAME_ID, status=AnnotationStatus.VERIFIED_EMPTY)
    assert empty.boxes == ()


def test_duplicate_boxes_are_rejected() -> None:
    box = _pig_box()
    with pytest.raises(InputDataError, match="Duplicate"):
        FrameAnnotation(
            frame_id=FRAME_ID,
            status=AnnotationStatus.ANNOTATED,
            boxes=(box, box),
        )


def test_manifest_uses_only_opaque_image_names_and_stable_serialization() -> None:
    record = AnnotationFrameRecord(
        frame_id=FRAME_ID,
        clip_id=CLIP_ID,
        split=DatasetSplit.TRAIN,
        image_relative_path=f"images/train/{FRAME_ID}.jpg",
        width=320,
        height=240,
        annotation_status=AnnotationStatus.ANNOTATED,
        bounding_box_count=1,
        checksum_sha256=CHECKSUM,
        validation_status=ManifestValidationStatus.PENDING,
    )
    manifest = AnnotationDatasetManifest(
        schema_version=1,
        dataset_id="synthetic-dataset",
        annotation_policy_version=ANNOTATION_POLICY_VERSION,
        class_map=((0, "pig"),),
        frames=(record,),
    )

    assert manifest_to_dict(manifest) == manifest_to_dict(manifest)
    assert manifest_to_dict(manifest)["class_map"] == [{"class_id": 0, "class_name": "pig"}]

    with pytest.raises(InputDataError, match="opaque frame ID"):
        AnnotationFrameRecord(
            frame_id=FRAME_ID,
            clip_id=CLIP_ID,
            split=DatasetSplit.TRAIN,
            image_relative_path="images/train/private-video-name.jpg",
            width=320,
            height=240,
            annotation_status=AnnotationStatus.VERIFIED_EMPTY,
            bounding_box_count=0,
            checksum_sha256=CHECKSUM,
        )
