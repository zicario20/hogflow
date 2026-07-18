"""Framework-neutral YOLO detection-label parsing and serialization."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from hogflow.annotation.models import AnnotationStatus, FrameAnnotation, PigAnnotation
from hogflow.core import InputDataError
from hogflow.evaluation.detection_models import CoordinateSpace, EvaluationBoundingBox
from hogflow.models import BoundingBox


def serialize_yolo(annotation: FrameAnnotation) -> str:
    """Serialize one frame annotation with deterministic box ordering."""

    if not isinstance(annotation, FrameAnnotation):
        raise InputDataError("annotation must be a FrameAnnotation.")
    if annotation.status is AnnotationStatus.VERIFIED_EMPTY:
        return ""
    if annotation.status is not AnnotationStatus.ANNOTATED:
        raise InputDataError("Review or excluded frames must not receive YOLO labels.")
    sorted_boxes = sorted(annotation.boxes, key=_box_sort_key)
    return "\n".join(_serialize_box(box) for box in sorted_boxes) + "\n"


def parse_yolo(text: str, *, frame_id: str, status: AnnotationStatus) -> FrameAnnotation:
    """Parse UTF-8 YOLO text under the explicit frame annotation status."""

    if not isinstance(text, str):
        raise InputDataError("YOLO label content must be text.")
    boxes: list[PigAnnotation] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            raise InputDataError(f"YOLO line {line_number} must not be blank.")
        fields = line.split()
        if len(fields) != 5:
            raise InputDataError(f"YOLO line {line_number} must contain exactly five values.")
        if fields[0] != "0":
            raise InputDataError(f"YOLO line {line_number} uses an unsupported class ID.")
        try:
            x_center, y_center, width, height = (float(value) for value in fields[1:])
        except ValueError as exc:
            raise InputDataError(f"YOLO line {line_number} contains malformed numbers.") from exc
        boxes.append(
            _annotation_from_yolo_values(
                x_center=x_center,
                y_center=y_center,
                width=width,
                height=height,
                line_number=line_number,
            )
        )
    return FrameAnnotation(frame_id=frame_id, status=status, boxes=tuple(boxes))


def write_yolo_label(annotation: FrameAnnotation, path: str | Path) -> None:
    """Atomically write one local UTF-8 YOLO label without changing its semantics."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(output_path, serialize_yolo(annotation))


def _annotation_from_yolo_values(
    *,
    x_center: float,
    y_center: float,
    width: float,
    height: float,
    line_number: int,
) -> PigAnnotation:
    if not 0.0 < width <= 1.0 or not 0.0 < height <= 1.0:
        raise InputDataError(f"YOLO line {line_number} width and height must be in (0, 1].")
    if not 0.0 <= x_center <= 1.0 or not 0.0 <= y_center <= 1.0:
        raise InputDataError(f"YOLO line {line_number} centers must be in [0, 1].")
    x_min = x_center - width / 2
    y_min = y_center - height / 2
    x_max = x_center + width / 2
    y_max = y_center + height / 2
    tolerance = 1e-12
    if x_min < -tolerance or y_min < -tolerance or x_max > 1 + tolerance or y_max > 1 + tolerance:
        raise InputDataError(f"YOLO line {line_number} box extends outside image boundaries.")
    box = BoundingBox(
        x_min=max(0.0, x_min),
        y_min=max(0.0, y_min),
        x_max=min(1.0, x_max),
        y_max=min(1.0, y_max),
    )
    return PigAnnotation(EvaluationBoundingBox(box, CoordinateSpace.NORMALIZED))


def _serialize_box(annotation: PigAnnotation) -> str:
    box = annotation.bounding_box.bounding_box
    values = (
        (box.x_min + box.x_max) / 2,
        (box.y_min + box.y_max) / 2,
        box.x_max - box.x_min,
        box.y_max - box.y_min,
    )
    return " ".join((str(annotation.class_id), *(_format_number(value) for value in values)))


def _box_sort_key(annotation: PigAnnotation) -> tuple[float, ...]:
    box = annotation.bounding_box.bounding_box
    return (float(annotation.class_id), box.x_min, box.y_min, box.x_max, box.y_max)


def _format_number(value: float) -> str:
    rendered = f"{value:.10f}".rstrip("0").rstrip(".")
    return rendered if rendered else "0"


def _atomic_write_text(path: Path, content: str) -> None:
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        temporary_path.replace(path)
    except OSError as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise InputDataError(f"Unable to write YOLO label for frame {path.stem!r}.") from exc


__all__ = ["parse_yolo", "serialize_yolo", "write_yolo_label"]
