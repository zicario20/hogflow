from types import SimpleNamespace

import numpy as np
import pytest
from _phase5_2_helpers import frame_packet
from _phase5_3_helpers import frame_detections
from _phase5_4_helpers import tracked_object, tracking_result

from hogflow.adapters.opencv_crossing_preview import OpenCVCrossingPreview
from hogflow.counting import (
    CrossingPreviewError,
    LiveCrossingConfiguration,
    NormalizedLine,
    NormalizedPoint,
    VirtualLineCrossingDetector,
)
from hogflow.detection.inference import LiveDetectionStats, PreviewAction
from hogflow.tracking import LiveTrackingTelemetry


class FakeCV2(SimpleNamespace):
    COLOR_RGB2BGR = 1
    FONT_HERSHEY_SIMPLEX = 2
    LINE_AA = 3

    def __init__(self, key: int = -1, *, fail: bool = False) -> None:
        super().__init__()
        self.key = key
        self.fail = fail
        self.labels: list[str] = []
        self.lines: list[tuple[tuple[int, int], tuple[int, int]]] = []
        self.circles: list[tuple[int, int]] = []
        self.destroyed: list[str] = []

    @staticmethod
    def cvtColor(frame, _code):
        return frame[..., ::-1]

    @staticmethod
    def rectangle(*_arguments) -> None:
        return None

    def line(self, _canvas, start, end, *_arguments) -> None:
        self.lines.append((start, end))

    def circle(self, _canvas, point, *_arguments) -> None:
        self.circles.append(point)

    def putText(self, _canvas, text, *_arguments) -> None:
        self.labels.append(text)

    def imshow(self, _name, _canvas) -> None:
        if self.fail:
            raise RuntimeError("display unavailable")

    def waitKey(self, _delay: int) -> int:
        return self.key

    def destroyWindow(self, name: str) -> None:
        self.destroyed.append(name)


def _configuration() -> LiveCrossingConfiguration:
    return LiveCrossingConfiguration(
        enabled=True,
        line=NormalizedLine(NormalizedPoint(0, 0.5), NormalizedPoint(1, 0.5)),
    )


def _detection_statistics() -> LiveDetectionStats:
    return LiveDetectionStats(
        frames_acquired=1,
        frames_submitted=1,
        frames_inferred=1,
        frames_skipped=0,
        source_frames_dropped=0,
        inference_failures=0,
        total_detections=0,
        preview_failures=0,
        average_inference_ms=1,
        p50_inference_ms=1,
        p95_inference_ms=1,
        effective_inference_fps=10,
        camera_fps=30,
        latest_frame_age_ms=2,
        maximum_frame_age_ms=2,
    )


def test_crossing_preview_draws_line_anchor_and_event_without_animal_total() -> None:
    configuration = _configuration()
    crossing_detector = VirtualLineCrossingDetector(configuration)
    crossing_detector.start("camera")
    first = tracking_result(
        0,
        (tracked_object(1, 1, 0.5, 3, 2),),
        width=8,
        height=6,
    )
    second = tracking_result(
        1,
        (tracked_object(1, 1, 3.5, 3, 5),),
        width=8,
        height=6,
    )
    crossing_detector.update(first)
    crossing = crossing_detector.update(second)
    tracking_telemetry = LiveTrackingTelemetry()
    cv2 = FakeCV2(27)
    preview = OpenCVCrossingPreview(configuration, cv2_module=cv2, numpy_module=np)

    action = preview.show_crossing(
        frame_packet(1),
        frame_detections(1),
        second,
        crossing,
        _detection_statistics(),
        tracking_telemetry.snapshot(),
        crossing_detector.statistics(),
    )
    preview.close()

    assert action is PreviewAction.STOP
    assert cv2.lines == [((0, 2), (7, 2))]
    assert cv2.circles
    assert any("crossing_event=negative_to_positive" in label for label in cv2.labels)
    assert all("total pigs" not in label.lower() for label in cv2.labels)
    assert cv2.destroyed == ["HogFlow live crossing"]


def test_crossing_preview_failure_is_sanitized() -> None:
    configuration = _configuration()
    crossing_detector = VirtualLineCrossingDetector(configuration)
    crossing_detector.start("camera")
    tracking = tracking_result(0, width=8, height=6)
    crossing = crossing_detector.update(tracking)
    preview = OpenCVCrossingPreview(
        configuration,
        cv2_module=FakeCV2(fail=True),
        numpy_module=np,
    )

    with pytest.raises(CrossingPreviewError, match="preview failed"):
        preview.show_crossing(
            frame_packet(0),
            frame_detections(0),
            tracking,
            crossing,
            _detection_statistics(),
            LiveTrackingTelemetry().snapshot(),
            crossing_detector.statistics(),
        )
