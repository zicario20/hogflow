"""Generic object tracking and directional line-crossing CLI composition root."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hogflow.adapters import OpenCVVideoSource, UltralyticsDetector, UltralyticsTracker
from hogflow.core import HogFlowError, configure_logging, get_logger
from hogflow.counting import CrossingDirection, CrossingEvent, DirectionalLineCounter, Line, Point
from hogflow.models import Frame
from hogflow.pipeline import GenericCountingPipeline
from hogflow.video.opencv_output import OpenCVAnnotatedVideoOutput

DEFAULT_MODEL = "yolo26n.pt"
TRACKER_CONFIG = "bytetrack.yaml"
TRACKER_STATE_TTL_FRAMES = 300
CLI_DIRECTION_CHOICES = ("negative-to-positive", "positive-to-negative")

_LOGGER = get_logger(__name__)


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
    """Create the backward-compatible generic counter command-line parser."""

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


def run_generic_counter(config: GenericCounterConfig) -> int:
    """Compose and run generic adapters, counting, logging, and annotation."""

    _validate_config(config)
    source = OpenCVVideoSource(config.input_path)
    output: OpenCVAnnotatedVideoOutput | None = None
    try:
        detector = UltralyticsDetector(
            config.model_name,
            config.class_name,
            config.confidence,
            config.device,
        )
        tracker = UltralyticsTracker(TRACKER_CONFIG)
        counter = DirectionalLineCounter(
            line=config.line,
            positive_direction=config.positive_direction,
            epsilon=config.line_epsilon,
        )
        output = OpenCVAnnotatedVideoOutput(
            config.output_path,
            fps=source.fps,
            width=source.width,
            height=source.height,
            line=config.line,
            class_name=config.class_name,
            show=config.show,
        )
        pipeline = GenericCountingPipeline(
            source,
            detector,
            tracker,
            counter,
            tracker_state_ttl_frames=TRACKER_STATE_TTL_FRAMES,
        )

        with config.events_path.open("w", encoding="utf-8", newline="\n") as event_file:

            def write_event(event: CrossingEvent, frame: Frame, current_count: int) -> None:
                timestamp = frame.timestamp_seconds
                if timestamp is None:
                    timestamp = frame.frame_index / source.fps
                payload = _event_payload(
                    event,
                    frame_index=frame.frame_index,
                    timestamp_seconds=timestamp,
                    current_positive_count=current_count,
                )
                event_file.write(json.dumps(payload, sort_keys=True) + "\n")

            summary = pipeline.run(
                max_frames=config.max_frames,
                on_frame=output,
                on_event=write_event,
            )
    finally:
        source.close()
        if output is not None:
            output.close()

    _LOGGER.info(
        "Generic counting run completed with %s processed frames and count %s",
        summary.processed_frames,
        summary.positive_count,
    )
    print(f"Processed frames: {summary.processed_frames}")
    print(f"Unique positive count: {summary.positive_count}")
    print(f"Annotated video: {config.output_path}")
    print(f"Crossing events: {config.events_path}")
    return summary.positive_count


def main(argv: Sequence[str] | None = None) -> int:
    """Run the generic counter command-line interface."""

    configure_logging()
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
    except (HogFlowError, OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
