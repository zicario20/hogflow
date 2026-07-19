from types import SimpleNamespace

import numpy as np
import pytest
from _phase5_2_helpers import frame_packet
from _phase5_3_helpers import frame_detections, pig_detection, tracking_request

from hogflow.adapters.opencv_tracking_preview import OpenCVTrackingPreview
from hogflow.detection.inference import LiveDetectionStats, PreviewAction
from hogflow.tracking import DeterministicIoUTracker, LiveTrackingTelemetry, TrackingPreviewError


class FakeCV2(SimpleNamespace):
    COLOR_RGB2BGR = 1
    FONT_HERSHEY_SIMPLEX = 2
    LINE_AA = 3

    def __init__(self, key: int = -1, *, fail: bool = False) -> None:
        super().__init__()
        self.key = key
        self.fail = fail
        self.labels: list[str] = []
        self.destroyed: list[str] = []

    @staticmethod
    def cvtColor(frame, _code):
        return frame[..., ::-1]

    @staticmethod
    def rectangle(*_arguments) -> None:
        return None

    def putText(self, _canvas, text, *_arguments) -> None:
        self.labels.append(text)

    def imshow(self, _name, _canvas) -> None:
        if self.fail:
            raise RuntimeError("display unavailable")

    def waitKey(self, _delay: int) -> int:
        return self.key

    def destroyWindow(self, name: str) -> None:
        self.destroyed.append(name)


def _detection_statistics() -> LiveDetectionStats:
    return LiveDetectionStats(
        frames_acquired=1,
        frames_submitted=1,
        frames_inferred=1,
        frames_skipped=0,
        source_frames_dropped=0,
        inference_failures=0,
        total_detections=1,
        preview_failures=0,
        average_inference_ms=2,
        p50_inference_ms=2,
        p95_inference_ms=2,
        effective_inference_fps=10,
        camera_fps=30,
        latest_frame_age_ms=3,
        maximum_frame_age_ms=3,
    )


def test_tracking_preview_shows_temporary_id_without_counting_and_stops_on_escape() -> None:
    cv2 = FakeCV2(27)
    tracker = DeterministicIoUTracker()
    tracker.start("camera")
    request = tracking_request(
        0,
        (pig_detection(),),
        width=8,
        height=6,
    )
    result = tracker.update(request)
    telemetry = LiveTrackingTelemetry()
    telemetry.record_request(request)
    telemetry.record_success(result)
    preview = OpenCVTrackingPreview(cv2_module=cv2, numpy_module=np)

    action = preview.show_tracking(
        frame_packet(0),
        frame_detections(0, request.detections),
        result,
        _detection_statistics(),
        telemetry.snapshot(),
    )
    preview.close()

    assert action is PreviewAction.STOP
    assert any("id=0" in label for label in cv2.labels)
    assert all("count" not in label.lower() for label in cv2.labels)
    assert cv2.destroyed == ["HogFlow live tracking"]


def test_tracking_preview_handles_no_tracks_and_sanitizes_failure() -> None:
    tracker = DeterministicIoUTracker()
    tracker.start("camera")
    request = tracking_request(0, width=8, height=6)
    result = tracker.update(request)
    telemetry = LiveTrackingTelemetry()
    telemetry.record_request(request)
    telemetry.record_success(result)
    preview = OpenCVTrackingPreview(cv2_module=FakeCV2(fail=True), numpy_module=np)

    with pytest.raises(TrackingPreviewError, match="preview failed"):
        preview.show_tracking(
            frame_packet(0),
            frame_detections(0),
            result,
            _detection_statistics(),
            telemetry.snapshot(),
        )
