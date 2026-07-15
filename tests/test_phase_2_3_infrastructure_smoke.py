import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from hogflow.adapters import OpenCVVideoSource
from hogflow.counting import CrossingDirection, DirectionalLineCounter, Line, Point
from hogflow.models import BoundingBox, Detection, Frame, Track
from hogflow.pipeline import GenericCountingPipeline
from hogflow.video.generic_counter import _event_payload
from hogflow.video.opencv_output import OpenCVAnnotatedVideoOutput

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


def _write_synthetic_video(path: Path) -> None:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        10.0,
        (64, 48),
    )
    assert writer.isOpened()
    try:
        for bottom_y in (20, 30, 40):
            frame = np.zeros((48, 64, 3), dtype=np.uint8)
            cv2.rectangle(frame, (27, bottom_y - 8), (37, bottom_y), (255, 255, 255), -1)
            writer.write(frame)
    finally:
        writer.release()


class _SyntheticDetector:
    def predict(self, frame: Frame) -> tuple[Detection, ...]:
        bottom_y = (20, 30, 40)[frame.frame_index]
        return (Detection(BoundingBox(27, bottom_y - 8, 37, bottom_y), 0.9, 0, "person"),)


class _SyntheticTracker:
    def update(
        self,
        _frame: Frame,
        detections: Sequence[Detection],
    ) -> tuple[Track, ...]:
        return tuple(Track(1, detection) for detection in detections)


def test_synthetic_video_pipeline_writes_openable_video_and_valid_jsonl(tmp_path: Path) -> None:
    input_path = tmp_path / "synthetic_input.avi"
    output_path = tmp_path / "synthetic_output.avi"
    events_path = tmp_path / "synthetic_events.jsonl"
    _write_synthetic_video(input_path)
    line = Line(Point(10, 30), Point(54, 30))
    source = OpenCVVideoSource(input_path)
    output = OpenCVAnnotatedVideoOutput(
        output_path,
        fps=source.fps,
        width=source.width,
        height=source.height,
        line=line,
        class_name="person",
    )
    counter = DirectionalLineCounter(
        line,
        CrossingDirection.NEGATIVE_TO_POSITIVE,
        epsilon=1.0,
    )
    pipeline = GenericCountingPipeline(
        source,
        _SyntheticDetector(),
        _SyntheticTracker(),
        counter,
    )

    try:
        with events_path.open("w", encoding="utf-8", newline="\n") as event_file:

            def write_event(event: object, frame: Frame, current_count: int) -> None:
                payload = _event_payload(
                    event,  # type: ignore[arg-type]
                    frame_index=frame.frame_index,
                    timestamp_seconds=frame.timestamp_seconds or 0.0,
                    current_positive_count=current_count,
                )
                event_file.write(json.dumps(payload, sort_keys=True) + "\n")

            summary = pipeline.run(on_frame=output, on_event=write_event)
    finally:
        output.close()

    assert summary.processed_frames == 3
    assert summary.crossing_event_count == 1
    assert summary.positive_count == 1
    assert output_path.stat().st_size > 0
    capture = cv2.VideoCapture(str(output_path))
    try:
        assert capture.isOpened()
        success, decoded_frame = capture.read()
        assert success is True
        assert decoded_frame is not None
    finally:
        capture.release()
    payloads = [
        json.loads(line_text)
        for line_text in events_path.read_text(encoding="utf-8").splitlines()
        if line_text
    ]
    assert len(payloads) == 1
    assert set(payloads[0]) == {
        "counted",
        "current_point",
        "current_positive_count",
        "direction",
        "frame_index",
        "previous_point",
        "timestamp_seconds",
        "tracker_id",
    }
