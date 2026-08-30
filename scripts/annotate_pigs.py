from __future__ import annotations

# ruff: noqa: E402
import argparse
import base64
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from hogflow.annotation.models import AnnotationStatus, FrameAnnotation, PigAnnotation
from hogflow.annotation.yolo import parse_yolo, write_yolo_label
from hogflow.core import InputDataError
from hogflow.evaluation.detection_models import CoordinateSpace, EvaluationBoundingBox
from hogflow.models import BoundingBox

_PLACEHOLDER_FRAME_ID = "0" * 24
_DISPLAY_MAX_WIDTH = 900
_DISPLAY_MAX_HEIGHT = 900


def normalized_box(
    *,
    native_width: int,
    native_height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
) -> tuple[float, float, float, float]:
    left = max(0, min(x0, x1))
    right = min(native_width, max(x0, x1))
    top = max(0, min(y0, y1))
    bottom = min(native_height, max(y0, y1))
    if left >= right or top >= bottom:
        raise ValueError("A pig box must have positive area.")
    values = (
        (left + right) / (2 * native_width),
        (top + bottom) / (2 * native_height),
        (right - left) / native_width,
        (bottom - top) / native_height,
    )
    return tuple(round(value, 6) for value in values)


def load_boxes(path: str | Path) -> list[tuple[float, float, float, float]]:
    label_path = Path(path)
    if not label_path.exists():
        return []
    text = label_path.read_text(encoding="utf-8")
    if not text.strip():
        return []
    try:
        annotation = parse_yolo(
            text,
            frame_id=_PLACEHOLDER_FRAME_ID,
            status=AnnotationStatus.ANNOTATED,
        )
    except InputDataError as exc:
        raise ValueError(str(exc).replace("class ID", "class 0")) from exc
    return [_box_tuple(box) for box in annotation.boxes]


def save_boxes(
    path: str | Path,
    boxes: Sequence[tuple[float, float, float, float]],
) -> None:
    label_path = Path(path)
    if not boxes:
        _atomic_write_text(label_path, "")
        return
    try:
        annotation = FrameAnnotation(
            frame_id=_PLACEHOLDER_FRAME_ID,
            status=AnnotationStatus.ANNOTATED,
            boxes=tuple(_pig_annotation(box) for box in boxes),
        )
        write_yolo_label(annotation, label_path)
    except InputDataError as exc:
        raise ValueError(str(exc)) from exc


@dataclass(frozen=True, slots=True)
class ExtractionFrameRecord:
    frame_id: str
    clip_id: str
    split: str
    image_relative_path: str
    width: int
    height: int
    checksum_sha256: str

    @property
    def label_relative_path(self) -> str:
        return f"labels/{self.split}/{self.frame_id}.txt"


@dataclass(frozen=True, slots=True)
class AnnotationProgress:
    total_frames: int
    completed_frames: int
    annotated_frames: int
    verified_empty_frames: int
    current_index: int


@dataclass(slots=True)
class AnnotationWorkspace:
    dataset_root: Path
    extraction_report_path: Path
    status_map_path: Path
    dataset_id: str
    records: tuple[ExtractionFrameRecord, ...]
    status_map: dict[str, Any]

    @classmethod
    def load(
        cls,
        *,
        dataset_root: str | Path,
        extraction_report_path: str | Path,
        status_map_path: str | Path,
    ) -> AnnotationWorkspace:
        dataset_path = Path(dataset_root)
        extraction_path = Path(extraction_report_path)
        status_path = Path(status_map_path)
        extraction_payload = _load_json_object(extraction_path, description="extraction report")
        records_payload = extraction_payload.get("records")
        dataset_id = extraction_payload.get("dataset_id", "phase10-3a-demo")
        if not isinstance(dataset_id, str) or not dataset_id.strip():
            raise ValueError("The extraction report dataset_id must be non-empty text.")
        if not isinstance(records_payload, list) or not records_payload:
            raise ValueError("The extraction report must contain a non-empty records array.")
        records: list[ExtractionFrameRecord] = []
        seen_frame_ids: set[str] = set()
        for item in records_payload:
            if not isinstance(item, dict):
                raise ValueError("Extraction report records must be JSON objects.")
            record = ExtractionFrameRecord(
                frame_id=_required_text(item, "frame_id"),
                clip_id=_required_text(item, "clip_id"),
                split=_required_text(item, "split"),
                image_relative_path=_required_text(item, "image_relative_path"),
                width=_required_positive_int(item, "width"),
                height=_required_positive_int(item, "height"),
                checksum_sha256=_required_text(item, "checksum_sha256"),
            )
            if record.frame_id in seen_frame_ids:
                raise ValueError(f"Duplicate frame_id {record.frame_id!r} in extraction report.")
            image_path = dataset_path / Path(record.image_relative_path)
            if not image_path.is_file():
                raise ValueError(f"Missing extracted image for frame {record.frame_id!r}.")
            seen_frame_ids.add(record.frame_id)
            records.append(record)
        status_map = load_status_map(status_path, dataset_id=dataset_id)
        if status_map["dataset_id"] != dataset_id:
            raise ValueError("Status map dataset_id does not match the extraction report.")
        _prune_unknown_status_entries(status_map, allowed_frame_ids=seen_frame_ids)
        return cls(
            dataset_root=dataset_path,
            extraction_report_path=extraction_path,
            status_map_path=status_path,
            dataset_id=dataset_id,
            records=tuple(records),
            status_map=status_map,
        )

    def image_path(self, record: ExtractionFrameRecord) -> Path:
        return self.dataset_root / Path(record.image_relative_path)

    def label_path(self, record: ExtractionFrameRecord) -> Path:
        return self.dataset_root / Path(record.label_relative_path)

    def persist_status_map(self) -> None:
        write_status_map(self.status_map_path, self.status_map)


@dataclass(slots=True)
class AnnotationSession:
    workspace: AnnotationWorkspace
    current_index: int = 0
    current_boxes: list[tuple[float, float, float, float]] | None = None
    selected_box_index: int | None = None

    def __post_init__(self) -> None:
        self.current_index = _resume_index(self.workspace)
        self.current_boxes = load_boxes(self.workspace.label_path(self.current_record))

    @property
    def current_record(self) -> ExtractionFrameRecord:
        return self.workspace.records[self.current_index]

    @property
    def progress(self) -> AnnotationProgress:
        frames = self.workspace.status_map["frames"]
        completed = 0
        annotated = 0
        verified_empty = 0
        for record in self.workspace.records:
            status = frames.get(record.frame_id, {}).get("status")
            if status in {
                AnnotationStatus.ANNOTATED.value,
                AnnotationStatus.VERIFIED_EMPTY.value,
                AnnotationStatus.EXCLUDED.value,
            }:
                completed += 1
            if status == AnnotationStatus.ANNOTATED.value:
                annotated += 1
            if status == AnnotationStatus.VERIFIED_EMPTY.value:
                verified_empty += 1
        return AnnotationProgress(
            total_frames=len(self.workspace.records),
            completed_frames=completed,
            annotated_frames=annotated,
            verified_empty_frames=verified_empty,
            current_index=self.current_index,
        )

    def set_boxes(self, boxes: Sequence[tuple[float, float, float, float]]) -> None:
        self.current_boxes = [tuple(round(value, 6) for value in box) for box in boxes]
        self.selected_box_index = None

    def save_current(self, *, status: str | AnnotationStatus | None = None) -> None:
        frame_status = _resolve_status(status=status, boxes=self.current_boxes or [])
        save_boxes(
            self.workspace.label_path(self.current_record),
            self.current_boxes or [],
        )
        self.workspace.status_map["frames"][self.current_record.frame_id] = {
            "bounding_box_count": len(self.current_boxes or []),
            "label_relative_path": self.current_record.label_relative_path,
            "status": frame_status.value,
        }
        self.workspace.persist_status_map()

    def go_to_next(self) -> None:
        if self.current_index >= len(self.workspace.records) - 1:
            return
        self.current_index += 1
        self._reload_current_boxes()

    def go_to_previous(self) -> None:
        if self.current_index <= 0:
            return
        self.current_index -= 1
        self._reload_current_boxes()

    def delete_selected_box(self) -> None:
        if self.selected_box_index is None:
            return
        del self.current_boxes[self.selected_box_index]
        self.selected_box_index = None

    def select_box_at_native_point(self, native_x: int, native_y: int) -> bool:
        for index, box in enumerate(self.current_boxes):
            if _contains_native_point(box, self.current_record, native_x, native_y):
                self.selected_box_index = index
                return True
        self.selected_box_index = None
        return False

    def replace_selected_box(
        self,
        *,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
    ) -> None:
        if self.selected_box_index is None:
            raise ValueError("Select a box before replacing it.")
        self.current_boxes[self.selected_box_index] = normalized_box(
            native_width=self.current_record.width,
            native_height=self.current_record.height,
            x0=x0,
            y0=y0,
            x1=x1,
            y1=y1,
        )

    def append_box(self, *, x0: int, y0: int, x1: int, y1: int) -> None:
        self.current_boxes.append(
            normalized_box(
                native_width=self.current_record.width,
                native_height=self.current_record.height,
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
            )
        )
        self.selected_box_index = len(self.current_boxes) - 1

    def _reload_current_boxes(self) -> None:
        self.current_boxes = load_boxes(self.workspace.label_path(self.current_record))
        self.selected_box_index = None


class PigAnnotatorApplication:
    def __init__(self, session: AnnotationSession) -> None:
        self._session = session
        self._replace_mode = False
        self._drag_start: tuple[int, int] | None = None
        self._drag_shape_id: int | None = None
        self._dirty = False
        self._tk = _load_tkinter()
        self._messagebox = self._tk.messagebox
        self._cv2 = _load_cv2()
        self._root = self._tk.Tk()
        self._root.title("HogFlow Pig Annotator")
        self._progress_var = self._tk.StringVar()
        self._status_var = self._tk.StringVar()
        self._canvas = self._tk.Canvas(self._root, bg="#101010", highlightthickness=0)
        self._image_handle: Any = None
        self._photo_image: Any = None
        self._display_scale = 1.0
        self._display_width = 0
        self._display_height = 0
        self._build_layout()
        self._load_current_frame()

    def run(self) -> int:
        self._root.mainloop()
        return 0

    def _build_layout(self) -> None:
        header = self._tk.Frame(self._root, padx=12, pady=12)
        header.pack(fill="x")
        self._tk.Label(
            header,
            textvariable=self._progress_var,
            anchor="w",
            font=("Segoe UI", 11, "bold"),
        ).pack(fill="x")
        self._tk.Label(
            header,
            textvariable=self._status_var,
            anchor="w",
            justify="left",
        ).pack(fill="x", pady=(4, 0))

        self._canvas.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self._canvas.bind("<ButtonPress-1>", self._on_left_press)
        self._canvas.bind("<B1-Motion>", self._on_left_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_left_release)

        controls = self._tk.Frame(self._root, padx=12, pady=(0, 12))
        controls.pack(fill="x")
        self._add_button(controls, "Previous", self._go_previous)
        self._add_button(controls, "Next", self._go_next)
        self._add_button(controls, "Save", self._save_current)
        self._add_button(controls, "Mark Empty", self._mark_empty)
        self._add_button(controls, "Delete Box", self._delete_box)
        self._add_button(controls, "Redraw Selected", self._toggle_replace_mode)
        self._add_button(controls, "Quit", self._close)

        self._root.bind("<Left>", lambda _event: self._go_previous())
        self._root.bind("<Right>", lambda _event: self._go_next())
        self._root.bind("<Control-s>", lambda _event: self._save_current())
        self._root.bind("<Delete>", lambda _event: self._delete_box())

    def _add_button(self, parent: Any, label: str, command: Any) -> None:
        self._tk.Button(parent, text=label, command=command, padx=10).pack(
            side="left",
            padx=(0, 8),
        )

    def _load_current_frame(self) -> None:
        record = self._session.current_record
        image = self._cv2.imread(str(self._session.workspace.image_path(record)))
        if image is None:
            raise ValueError(f"Unable to read image for frame {record.frame_id!r}.")
        self._display_scale = min(
            _DISPLAY_MAX_WIDTH / record.width,
            _DISPLAY_MAX_HEIGHT / record.height,
            1.0,
        )
        self._display_width = max(1, int(round(record.width * self._display_scale)))
        self._display_height = max(1, int(round(record.height * self._display_scale)))
        if self._display_scale != 1.0:
            image = self._cv2.resize(
                image,
                (self._display_width, self._display_height),
                interpolation=self._cv2.INTER_AREA,
            )
        encoded_ok, encoded = self._cv2.imencode(".png", image)
        if not encoded_ok:
            raise ValueError(f"Unable to render image for frame {record.frame_id!r}.")
        self._photo_image = self._tk.PhotoImage(
            data=base64.b64encode(encoded.tobytes()).decode("ascii")
        )
        self._canvas.config(width=self._display_width, height=self._display_height)
        self._canvas.delete("all")
        self._image_handle = self._canvas.create_image(0, 0, anchor="nw", image=self._photo_image)
        self._render_boxes()
        self._update_labels()
        self._dirty = False
        self._replace_mode = False

    def _render_boxes(self) -> None:
        for index, box in enumerate(self._session.current_boxes):
            x0, y0, x1, y1 = _denormalize_box(
                box,
                self._session.current_record.width,
                self._session.current_record.height,
            )
            display_x0, display_y0 = self._native_to_display(x0, y0)
            display_x1, display_y1 = self._native_to_display(x1, y1)
            color = "#facc15" if index == self._session.selected_box_index else "#22c55e"
            self._canvas.create_rectangle(
                display_x0,
                display_y0,
                display_x1,
                display_y1,
                outline=color,
                width=2,
            )
            self._canvas.create_text(
                display_x0 + 4,
                max(8, display_y0 + 8),
                anchor="w",
                text=f"pig {index + 1}",
                fill=color,
            )

    def _update_labels(self) -> None:
        record = self._session.current_record
        progress = self._session.progress
        self._progress_var.set(
            (
                f"Frame {progress.current_index + 1} / {progress.total_frames}  "
                f"| Completed {progress.completed_frames}  "
                f"| Annotated {progress.annotated_frames}  "
                f"| Empty {progress.verified_empty_frames}"
            )
        )
        mode_label = "replace selected box" if self._replace_mode else "draw/select"
        self._status_var.set(
            (
                f"{record.frame_id}  "
                f"| Split {record.split}  "
                f"| Boxes {len(self._session.current_boxes)}  "
                f"| Mode {mode_label}"
            )
        )

    def _go_previous(self) -> None:
        if not self._confirm_navigation():
            return
        self._session.go_to_previous()
        self._load_current_frame()

    def _go_next(self) -> None:
        if not self._confirm_navigation():
            return
        self._session.go_to_next()
        self._load_current_frame()

    def _save_current(self) -> None:
        try:
            self._session.save_current()
        except ValueError as exc:
            self._messagebox.showerror("Save failed", str(exc))
            return
        self._dirty = False
        self._update_labels()

    def _mark_empty(self) -> None:
        self._session.set_boxes([])
        self._session.save_current(status=AnnotationStatus.VERIFIED_EMPTY)
        self._dirty = False
        self._load_current_frame()

    def _delete_box(self) -> None:
        self._session.delete_selected_box()
        self._dirty = True
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo_image)
        self._render_boxes()
        self._update_labels()

    def _toggle_replace_mode(self) -> None:
        if self._session.selected_box_index is None:
            self._messagebox.showinfo("Select a box", "Click an existing pig box before redrawing.")
            return
        self._replace_mode = not self._replace_mode
        self._update_labels()

    def _close(self) -> None:
        if not self._confirm_navigation():
            return
        self._root.destroy()

    def _confirm_navigation(self) -> bool:
        if not self._dirty:
            return True
        answer = self._messagebox.askyesnocancel(
            "Unsaved changes",
            "Save the current frame before moving on?",
        )
        if answer is None:
            return False
        if answer:
            self._save_current()
            return not self._dirty
        return True

    def _on_left_press(self, event: Any) -> None:
        native_x, native_y = self._display_to_native(event.x, event.y)
        if not self._replace_mode and self._session.select_box_at_native_point(native_x, native_y):
            self._canvas.delete("all")
            self._canvas.create_image(0, 0, anchor="nw", image=self._photo_image)
            self._render_boxes()
            self._update_labels()
            return
        self._drag_start = (native_x, native_y)
        self._drag_shape_id = self._canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="#38bdf8",
            dash=(4, 2),
            width=2,
        )

    def _on_left_drag(self, event: Any) -> None:
        if self._drag_shape_id is None:
            return
        self._canvas.coords(
            self._drag_shape_id,
            self._canvas.canvasx(event.x),
            self._canvas.canvasy(event.y),
            event.x,
            event.y,
        )

    def _on_left_release(self, event: Any) -> None:
        if self._drag_start is None:
            return
        start_x, start_y = self._drag_start
        native_x, native_y = self._display_to_native(event.x, event.y)
        self._drag_start = None
        if self._drag_shape_id is not None:
            self._canvas.delete(self._drag_shape_id)
            self._drag_shape_id = None
        try:
            if self._replace_mode:
                self._session.replace_selected_box(
                    x0=start_x,
                    y0=start_y,
                    x1=native_x,
                    y1=native_y,
                )
                self._replace_mode = False
            else:
                self._session.append_box(
                    x0=start_x,
                    y0=start_y,
                    x1=native_x,
                    y1=native_y,
                )
        except ValueError:
            return
        self._dirty = True
        self._canvas.delete("all")
        self._canvas.create_image(0, 0, anchor="nw", image=self._photo_image)
        self._render_boxes()
        self._update_labels()

    def _display_to_native(self, display_x: int, display_y: int) -> tuple[int, int]:
        native_x = int(round(max(0, min(display_x, self._display_width)) / self._display_scale))
        native_y = int(round(max(0, min(display_y, self._display_height)) / self._display_scale))
        return native_x, native_y

    def _native_to_display(self, native_x: int, native_y: int) -> tuple[int, int]:
        return (
            int(round(native_x * self._display_scale)),
            int(round(native_y * self._display_scale)),
        )


def load_status_map(path: str | Path, *, dataset_id: str) -> dict[str, Any]:
    status_path = Path(path)
    if not status_path.exists():
        return {"dataset_id": dataset_id, "frames": {}}
    payload = _load_json_object(status_path, description="annotation status map")
    frames = payload.get("frames")
    if not isinstance(frames, dict):
        raise ValueError("The annotation status map must contain a frames object.")
    payload.setdefault("dataset_id", dataset_id)
    return payload


def write_status_map(path: str | Path, payload: dict[str, Any]) -> None:
    _atomic_write_json(Path(path), payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local-only HogFlow pig box annotation helper.")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--manifest", "--extraction-report", dest="extraction_report", type=Path, required=True
    )
    parser.add_argument("--status-map", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    workspace = AnnotationWorkspace.load(
        dataset_root=arguments.dataset,
        extraction_report_path=arguments.extraction_report,
        status_map_path=arguments.status_map,
    )
    session = AnnotationSession(workspace)
    return PigAnnotatorApplication(session).run()


def _resolve_status(
    *,
    status: str | AnnotationStatus | None,
    boxes: Sequence[tuple[float, float, float, float]],
) -> AnnotationStatus:
    if status is None:
        return AnnotationStatus.ANNOTATED if boxes else AnnotationStatus.VERIFIED_EMPTY
    if isinstance(status, AnnotationStatus):
        resolved = status
    else:
        try:
            resolved = AnnotationStatus(status)
        except ValueError as exc:
            raise ValueError("Unsupported annotation status.") from exc
    if resolved is AnnotationStatus.ANNOTATED and not boxes:
        raise ValueError("Annotated frames must contain at least one pig box.")
    if resolved is not AnnotationStatus.ANNOTATED and boxes:
        raise ValueError("Only annotated frames may contain pig boxes.")
    return resolved


def _resume_index(workspace: AnnotationWorkspace) -> int:
    frames = workspace.status_map["frames"]
    for index, record in enumerate(workspace.records):
        status = frames.get(record.frame_id, {}).get("status")
        if status not in {
            AnnotationStatus.ANNOTATED.value,
            AnnotationStatus.VERIFIED_EMPTY.value,
            AnnotationStatus.EXCLUDED.value,
        }:
            return index
    return max(0, len(workspace.records) - 1)


def _required_text(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Extraction report field {field_name!r} must be non-empty text.")
    return value


def _required_positive_int(payload: dict[str, Any], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"Extraction report field {field_name!r} must be a positive integer.")
    return value


def _prune_unknown_status_entries(
    status_map: dict[str, Any], *, allowed_frame_ids: set[str]
) -> None:
    frames = status_map["frames"]
    for frame_id in tuple(frames):
        if frame_id not in allowed_frame_ids:
            del frames[frame_id]


def _pig_annotation(box: tuple[float, float, float, float]) -> PigAnnotation:
    x_center, y_center, width, height = box
    bounding_box = BoundingBox(
        x_min=x_center - width / 2,
        y_min=y_center - height / 2,
        x_max=x_center + width / 2,
        y_max=y_center + height / 2,
    )
    return PigAnnotation(
        EvaluationBoundingBox(bounding_box, CoordinateSpace.NORMALIZED),
    )


def _box_tuple(annotation: PigAnnotation) -> tuple[float, float, float, float]:
    box = annotation.bounding_box.bounding_box
    values = (
        (box.x_min + box.x_max) / 2,
        (box.y_min + box.y_max) / 2,
        box.x_max - box.x_min,
        box.y_max - box.y_min,
    )
    return tuple(round(value, 6) for value in values)


def _denormalize_box(
    box: tuple[float, float, float, float],
    native_width: int,
    native_height: int,
) -> tuple[int, int, int, int]:
    x_center, y_center, width, height = box
    x0 = int(round((x_center - width / 2) * native_width))
    y0 = int(round((y_center - height / 2) * native_height))
    x1 = int(round((x_center + width / 2) * native_width))
    y1 = int(round((y_center + height / 2) * native_height))
    return x0, y0, x1, y1


def _contains_native_point(
    box: tuple[float, float, float, float],
    record: ExtractionFrameRecord,
    native_x: int,
    native_y: int,
) -> bool:
    x0, y0, x1, y1 = _denormalize_box(box, record.width, record.height)
    return x0 <= native_x <= x1 and y0 <= native_y <= y1


def _load_tkinter() -> Any:
    import tkinter as tk
    from tkinter import messagebox

    tk.messagebox = messagebox
    return tk


def _load_cv2() -> Any:
    import cv2

    return cv2


def _load_json_object(path: Path, *, description: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"The local {description} is missing or is not a file.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"The local {description} is not valid UTF-8 JSON.") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"The local {description} must contain one JSON object.")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    content = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    _atomic_write_text(path, content)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        raise ValueError(f"Unable to write {path.name!r}.") from exc


if __name__ == "__main__":
    raise SystemExit(main())
