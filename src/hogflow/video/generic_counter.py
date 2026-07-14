"""Phase 1 generic object tracking and directional line-crossing CLI."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from hogflow.counting.line_crossing import (
    CrossingDirection,
    CrossingEvent,
    DirectionalLineCounter,
    Line,
    Point,
)

DEFAULT_MODEL = "yolo26n.pt"
TRACKER_CONFIG = "bytetrack.yaml"
TRACKER_STATE_TTL_FRAMES = 300
CLI_DIRECTION_CHOICES = ("negative-to-positive", "positive-to-negative")


@dataclass(frozen=True, slots=True)
class GenericCounterConfig:
    """Validated runtime settings for one generic counter run."""

    input_path: Path
    output_path: Path
    events_path: Path
    class_name: str
    line: Line
    positive_direction: CrossingDirection
    confidence: float = 0.35
    line_epsilon: float = 1.0
    model_name: str = DEFAULT_MODEL
    device: str | None = None
    show: bool = False
    max_frames: int | None = None


def parse_point(value: str) -> Point:
    """Parse an ``x,y`` CLI value into a point."""

    parts = value.split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("expected coordinates in x,y format")
    try:
        return Point(x=float(parts[0].strip()), y=float(parts[1].strip()))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("coordinates must be finite numbers") from exc


def positive_integer(value: str) -> int:
    """Parse a positive integer CLI value."""

    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("expected a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    """Create the Phase 1 command-line parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Count unique tracked people or vehicles crossing a configured "
            "directional line in a local video."
        )
    )
    parser.add_argument("--input", required=True, type=Path, help="Local input video file")
    parser.add_argument("--output", required=True, type=Path, help="Annotated output video")
    parser.add_argument("--events", required=True, type=Path, help="JSONL crossing event log")
    parser.add_argument("--class", dest="class_name", required=True, help="Detector class name")
    parser.add_argument("--line-start", required=True, type=parse_point, help="Line start as x,y")
    parser.add_argument("--line-end", required=True, type=parse_point, help="Line end as x,y")
    parser.add_argument(
        "--positive-direction",
        required=True,
        choices=CLI_DIRECTION_CHOICES,
        help="Side transition that contributes to the unique positive count",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=0.35,
        help="Detector confidence threshold in the range (0, 1] (default: 0.35)",
    )
    parser.add_argument(
        "--line-epsilon",
        type=float,
        default=1.0,
        help="Near-line tolerance in pixels (default: 1.0)",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Ultralytics detection model (default: {DEFAULT_MODEL})",
    )
    parser.add_argument("--device", help="Optional Ultralytics device, for example cpu or 0")
    parser.add_argument("--show", action="store_true", help="Display an optional OpenCV window")
    parser.add_argument(
        "--max-frames",
        type=positive_integer,
        help="Stop after this many frames for a bounded integration run",
    )
    return parser


def _validate_config(config: GenericCounterConfig) -> None:
    if not config.input_path.exists():
        raise ValueError(f"Input video does not exist: {config.input_path}")
    if not config.input_path.is_file():
        raise ValueError(f"Input path is not a file: {config.input_path}")
    if not 0.0 < config.confidence <= 1.0:
        raise ValueError("Confidence must be greater than 0 and at most 1.")
    if config.line_epsilon < 0:
        raise ValueError("Line epsilon must be non-negative.")
    if not config.class_name.strip():
        raise ValueError("Requested class must not be empty.")

    input_resolved = config.input_path.resolve()
    output_resolved = config.output_path.resolve()
    events_resolved = config.events_path.resolve()
    if output_resolved == input_resolved:
        raise ValueError("Output video must not overwrite the input video.")
    if events_resolved in {input_resolved, output_resolved}:
        raise ValueError("Event log path must differ from input and output video paths.")

    for path in (config.output_path, config.events_path):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ValueError(f"Could not create parent directory for {path}: {exc}") from exc


def _load_runtime_dependencies() -> tuple[Any, Any, Any]:
    try:
        import cv2
        import supervision as sv
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError(
            'Phase 1 runtime dependencies are missing. Install with pip install -e ".[dev]".'
        ) from exc
    return cv2, sv, YOLO


def _class_names_by_id(names: Mapping[Any, Any] | Sequence[Any]) -> dict[int, str]:
    if isinstance(names, Mapping):
        return {int(class_id): str(name) for class_id, name in names.items()}
    return {class_id: str(name) for class_id, name in enumerate(names)}


def _resolve_class_id(class_name: str, names: Mapping[Any, Any] | Sequence[Any]) -> int:
    names_by_id = _class_names_by_id(names)
    matches = [class_id for class_id, name in names_by_id.items() if name == class_name]
    if matches:
        return matches[0]

    available = ", ".join(sorted(names_by_id.values()))
    raise ValueError(
        f"Requested class {class_name!r} is not available in the selected model. "
        f"Available classes: {available}"
    )


def _bottom_center(xyxy: Sequence[float]) -> Point:
    x1, _y1, x2, y2 = xyxy
    return Point(x=(float(x1) + float(x2)) / 2.0, y=float(y2))


def _event_payload(
    event: CrossingEvent,
    *,
    frame_index: int,
    timestamp_seconds: float,
    current_positive_count: int,
) -> dict[str, object]:
    return {
        "frame_index": frame_index,
        "timestamp_seconds": round(timestamp_seconds, 6),
        "tracker_id": event.tracker_id,
        "direction": event.direction.value,
        "counted": event.counted,
        "previous_point": {
            "x": event.previous_point.x,
            "y": event.previous_point.y,
        },
        "current_point": {
            "x": event.current_point.x,
            "y": event.current_point.y,
        },
        "current_positive_count": current_positive_count,
    }


def _forget_inactive_tracker_states(
    counter: DirectionalLineCounter,
    last_seen_frame: dict[int, int],
    frame_index: int,
) -> None:
    stale_ids = [
        tracker_id
        for tracker_id, last_seen in last_seen_frame.items()
        if frame_index - last_seen > TRACKER_STATE_TTL_FRAMES
    ]
    for tracker_id in stale_ids:
        counter.forget_tracker(tracker_id)
        del last_seen_frame[tracker_id]


def run_generic_counter(config: GenericCounterConfig) -> int:
    """Run generic detection, tracking, counting, logging, and annotation."""

    _validate_config(config)
    cv2, sv, yolo_class = _load_runtime_dependencies()

    try:
        model = yolo_class(config.model_name)
    except Exception as exc:
        raise RuntimeError(f"Could not load detector model {config.model_name!r}: {exc}") from exc

    class_id = _resolve_class_id(config.class_name, model.names)
    capture = cv2.VideoCapture(str(config.input_path))
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(f"OpenCV could not open input video: {config.input_path}")

    fps = float(capture.get(cv2.CAP_PROP_FPS))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps <= 0 or width <= 0 or height <= 0:
        capture.release()
        raise RuntimeError("Input video has invalid FPS or frame dimensions.")

    fourcc_name = "XVID" if config.output_path.suffix.lower() == ".avi" else "mp4v"
    writer = cv2.VideoWriter(
        str(config.output_path),
        cv2.VideoWriter_fourcc(*fourcc_name),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        capture.release()
        writer.release()
        raise RuntimeError(f"OpenCV could not create output video: {config.output_path}")

    counter = DirectionalLineCounter(
        line=config.line,
        positive_direction=config.positive_direction,
        epsilon=config.line_epsilon,
    )
    box_annotator = sv.BoxAnnotator()
    label_annotator = sv.LabelAnnotator()
    last_seen_frame: dict[int, int] = {}
    frame_index = 0

    try:
        with config.events_path.open("w", encoding="utf-8", newline="\n") as event_file:
            while capture.isOpened():
                if config.max_frames is not None and frame_index >= config.max_frames:
                    break

                success, frame = capture.read()
                if not success:
                    break

                track_arguments: dict[str, object] = {
                    "source": frame,
                    "persist": True,
                    "tracker": TRACKER_CONFIG,
                    "classes": [class_id],
                    "conf": config.confidence,
                    "verbose": False,
                }
                if config.device is not None:
                    track_arguments["device"] = config.device

                # Ultralytics applies class/confidence filtering before ByteTrack.
                results = model.track(**track_arguments)
                if not results:
                    raise RuntimeError(
                        f"Detector returned no result container at frame {frame_index}."
                    )

                detections = sv.Detections.from_ultralytics(results[0])
                tracker_ids = detections.tracker_id
                if tracker_ids is not None:
                    for bounding_box, raw_tracker_id in zip(
                        detections.xyxy,
                        tracker_ids,
                        strict=True,
                    ):
                        tracker_id = int(raw_tracker_id)
                        if tracker_id < 0:
                            continue
                        last_seen_frame[tracker_id] = frame_index
                        event = counter.update(tracker_id, _bottom_center(bounding_box))
                        if event is None:
                            continue
                        payload = _event_payload(
                            event,
                            frame_index=frame_index,
                            timestamp_seconds=frame_index / fps,
                            current_positive_count=counter.count,
                        )
                        event_file.write(json.dumps(payload, sort_keys=True) + "\n")

                _forget_inactive_tracker_states(counter, last_seen_frame, frame_index)

                annotated_frame = box_annotator.annotate(
                    scene=frame.copy(),
                    detections=detections,
                )
                if tracker_ids is None:
                    labels = [f"{config.class_name} (untracked)" for _ in range(len(detections))]
                else:
                    labels = [
                        f"{config.class_name} #{int(tracker_id)}" for tracker_id in tracker_ids
                    ]
                annotated_frame = label_annotator.annotate(
                    scene=annotated_frame,
                    detections=detections,
                    labels=labels,
                )

                line_start = (round(config.line.start.x), round(config.line.start.y))
                line_end = (round(config.line.end.x), round(config.line.end.y))
                cv2.line(annotated_frame, line_start, line_end, (0, 255, 255), 3)
                cv2.putText(
                    annotated_frame,
                    f"COUNT: {counter.count}",
                    (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.0,
                    (0, 255, 0),
                    2,
                    cv2.LINE_AA,
                )
                cv2.putText(
                    annotated_frame,
                    f"CLASS: {config.class_name}",
                    (20, 75),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (255, 255, 255),
                    2,
                    cv2.LINE_AA,
                )
                writer.write(annotated_frame)

                if config.show:
                    cv2.imshow("HogFlow Phase 1 Generic Counter", annotated_frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        frame_index += 1
                        break

                frame_index += 1
    finally:
        capture.release()
        writer.release()
        if config.show:
            cv2.destroyAllWindows()

    print(f"Processed frames: {frame_index}")
    print(f"Unique positive count: {counter.count}")
    print(f"Annotated video: {config.output_path}")
    print(f"Crossing events: {config.events_path}")
    return counter.count


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Phase 1 generic counter command-line interface."""

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        line = Line(start=args.line_start, end=args.line_end)
        config = GenericCounterConfig(
            input_path=args.input,
            output_path=args.output,
            events_path=args.events,
            class_name=args.class_name,
            line=line,
            positive_direction=CrossingDirection(args.positive_direction.replace("-", "_")),
            confidence=args.confidence,
            line_epsilon=args.line_epsilon,
            model_name=args.model,
            device=args.device,
            show=args.show,
            max_frames=args.max_frames,
        )
        run_generic_counter(config)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
