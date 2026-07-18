import hashlib
from pathlib import Path

import cv2
import numpy as np

from hogflow.annotation.manifest import write_annotation_manifest
from hogflow.annotation.models import (
    ANNOTATION_POLICY_VERSION,
    AnnotationDatasetManifest,
    AnnotationFrameRecord,
    AnnotationStatus,
    DatasetSplit,
    FrameAnnotation,
    PigAnnotation,
)
from hogflow.annotation.yolo import write_yolo_label
from hogflow.evaluation import CoordinateSpace, EvaluationBoundingBox
from hogflow.models import BoundingBox

TRAIN_CLIP = "1" * 24
VALIDATION_CLIP = "2" * 24
TEST_CLIP = "3" * 24
TRAIN_FRAME = "a" * 24
VALIDATION_FRAME = "b" * 24
TEST_FRAME = "c" * 24


def pig_annotation(
    box: tuple[float, float, float, float] = (0.2, 0.2, 0.6, 0.6),
) -> PigAnnotation:
    return PigAnnotation(EvaluationBoundingBox(BoundingBox(*box), CoordinateSpace.NORMALIZED))


def create_prepared_dataset(
    root: Path,
    *,
    include_test: bool = True,
    validation_status: AnnotationStatus = AnnotationStatus.ANNOTATED,
) -> Path:
    records = [
        _write_frame(
            root,
            frame_id=TRAIN_FRAME,
            clip_id=TRAIN_CLIP,
            split=DatasetSplit.TRAIN,
            status=AnnotationStatus.ANNOTATED,
            image_value=30,
        ),
        _write_frame(
            root,
            frame_id=VALIDATION_FRAME,
            clip_id=VALIDATION_CLIP,
            split=DatasetSplit.VALIDATION,
            status=validation_status,
            image_value=90,
        ),
    ]
    if include_test:
        records.append(
            _write_frame(
                root,
                frame_id=TEST_FRAME,
                clip_id=TEST_CLIP,
                split=DatasetSplit.TEST,
                status=AnnotationStatus.VERIFIED_EMPTY,
                image_value=150,
            )
        )
    manifest = AnnotationDatasetManifest(
        schema_version=1,
        dataset_id="synthetic-phase4-3",
        annotation_policy_version=ANNOTATION_POLICY_VERSION,
        class_map=((0, "pig"),),
        frames=tuple(sorted(records, key=lambda record: record.frame_id)),
    )
    manifest_path = root / "metadata" / "dataset_manifest.json"
    write_annotation_manifest(manifest, manifest_path)
    return manifest_path


def _write_frame(
    root: Path,
    *,
    frame_id: str,
    clip_id: str,
    split: DatasetSplit,
    status: AnnotationStatus,
    image_value: int,
) -> AnnotationFrameRecord:
    image_relative = f"images/{split.value}/{frame_id}.png"
    image_path = root / Path(*image_relative.split("/"))
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image = np.full((100, 120, 3), image_value, dtype=np.uint8)
    encoded, content = cv2.imencode(".png", image)
    assert encoded
    image_path.write_bytes(content.tobytes())
    boxes = (pig_annotation(),) if status is AnnotationStatus.ANNOTATED else ()
    label_path = root / "labels" / split.value / f"{frame_id}.txt"
    if status in {AnnotationStatus.ANNOTATED, AnnotationStatus.VERIFIED_EMPTY}:
        write_yolo_label(FrameAnnotation(frame_id, status, boxes), label_path)
    return AnnotationFrameRecord(
        frame_id=frame_id,
        clip_id=clip_id,
        split=split,
        image_relative_path=image_relative,
        width=120,
        height=100,
        annotation_status=status,
        bounding_box_count=len(boxes),
        checksum_sha256=hashlib.sha256(image_path.read_bytes()).hexdigest(),
    )


class FakeBoxes:
    def __init__(self, xyxy=(), confidence=(), classes=()) -> None:
        self.xyxy = list(xyxy)
        self.conf = list(confidence)
        self.cls = list(classes)

    def __len__(self) -> int:
        return len(self.xyxy)


class FakePredictionResult:
    def __init__(self, boxes: FakeBoxes | None = None) -> None:
        self.boxes = boxes or FakeBoxes()


class FakeFrameworkMetrics:
    def __init__(self, values: dict[str, float]) -> None:
        self.results_dict = values


class FakeYOLOModel:
    def __init__(self, source: str, state: dict[str, object]) -> None:
        self.source = source
        self.state = state
        self.trainer = None

    def train(self, **kwargs):
        self.state["train_source"] = self.source
        self.state["train_kwargs"] = kwargs
        checkpoint = Path(kwargs["project"]) / str(kwargs["name"]) / "weights" / "best.pt"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_bytes(b"synthetic checkpoint")
        self.trainer = type(
            "FakeTrainerState",
            (),
            {"best": checkpoint, "last": checkpoint},
        )()
        return FakeFrameworkMetrics({"metrics/mAP50(B)": 0.5, "fitness": 0.4})

    def val(self, **kwargs):
        self.state["val_source"] = self.source
        self.state["val_kwargs"] = kwargs
        return FakeFrameworkMetrics(
            {
                "metrics/precision(B)": 0.75,
                "metrics/recall(B)": 0.5,
                "metrics/mAP50(B)": 0.6,
            }
        )

    def predict(self, **kwargs):
        self.state["predict_kwargs"] = kwargs
        results = self.state.get("prediction_results")
        if results is not None:
            return results
        return [
            FakePredictionResult(
                FakeBoxes(
                    xyxy=((24.0, 20.0, 72.0, 60.0),),
                    confidence=(0.9,),
                    classes=(0,),
                )
            )
            for _source in kwargs["source"]
        ]


def fake_yolo_factory(state: dict[str, object]):
    def factory(source: str) -> FakeYOLOModel:
        model = FakeYOLOModel(source, state)
        state.setdefault("models", []).append(model)
        return model

    return factory
