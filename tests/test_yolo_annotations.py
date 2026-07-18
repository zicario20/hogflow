from pathlib import Path

import pytest

from hogflow.annotation.models import AnnotationStatus, FrameAnnotation, PigAnnotation
from hogflow.annotation.yolo import parse_yolo, serialize_yolo, write_yolo_label
from hogflow.core import InputDataError
from hogflow.evaluation import CoordinateSpace, EvaluationBoundingBox
from hogflow.models import BoundingBox

FRAME_ID = "d" * 24


def _box(x_min: float, y_min: float, x_max: float, y_max: float) -> PigAnnotation:
    return PigAnnotation(
        EvaluationBoundingBox(
            BoundingBox(x_min, y_min, x_max, y_max),
            CoordinateSpace.NORMALIZED,
        )
    )


def test_parse_serialize_round_trip_is_stable_and_sorted() -> None:
    annotation = FrameAnnotation(
        frame_id=FRAME_ID,
        status=AnnotationStatus.ANNOTATED,
        boxes=(_box(0.6, 0.6, 0.9, 0.9), _box(0.1, 0.2, 0.5, 0.8)),
    )

    serialized = serialize_yolo(annotation)
    parsed = parse_yolo(serialized, frame_id=FRAME_ID, status=AnnotationStatus.ANNOTATED)

    assert serialized.splitlines()[0] == "0 0.3 0.5 0.4 0.6"
    assert serialize_yolo(parsed) == serialized


@pytest.mark.parametrize(
    "content",
    [
        "1 0.5 0.5 0.2 0.2\n",
        "0 0.5 0.5 0.2\n",
        "0 text 0.5 0.2 0.2\n",
        "0 nan 0.5 0.2 0.2\n",
        "0 inf 0.5 0.2 0.2\n",
        "0 0.5 0.5 0 0.2\n",
        "0 0.95 0.5 0.2 0.2\n",
        "0 0.5 0.5 1.1 0.2\n",
        "\n",
    ],
)
def test_parse_rejects_malformed_or_out_of_bounds_rows(content: str) -> None:
    with pytest.raises(InputDataError):
        parse_yolo(content, frame_id=FRAME_ID, status=AnnotationStatus.ANNOTATED)


def test_parse_rejects_duplicate_boxes() -> None:
    line = "0 0.5 0.5 0.2 0.2\n"
    with pytest.raises(InputDataError, match="Duplicate"):
        parse_yolo(line + line, frame_id=FRAME_ID, status=AnnotationStatus.ANNOTATED)


def test_empty_label_is_allowed_only_for_verified_empty() -> None:
    empty = parse_yolo("", frame_id=FRAME_ID, status=AnnotationStatus.VERIFIED_EMPTY)
    assert empty.boxes == ()
    assert serialize_yolo(empty) == ""

    with pytest.raises(InputDataError, match="at least one"):
        parse_yolo("", frame_id=FRAME_ID, status=AnnotationStatus.ANNOTATED)
    with pytest.raises(InputDataError, match="must not receive"):
        serialize_yolo(FrameAnnotation(FRAME_ID, AnnotationStatus.EXCLUDED))


def test_yolo_label_write_is_utf8_and_deterministic(tmp_path: Path) -> None:
    annotation = FrameAnnotation(
        FRAME_ID,
        AnnotationStatus.ANNOTATED,
        (_box(0.1, 0.1, 0.9, 0.9),),
    )
    destination = tmp_path / "labels" / f"{FRAME_ID}.txt"

    write_yolo_label(annotation, destination)

    assert destination.read_text(encoding="utf-8") == "0 0.5 0.5 0.8 0.8\n"
