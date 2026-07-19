from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pytest
from _phase5_2_helpers import frame_packet

from hogflow.adapters.opencv_detection_preview import OpenCVDetectionPreview
from hogflow.detection.errors import DetectionPreviewError
from hogflow.detection.inference import FrameDetections, LiveDetectionStats, PreviewAction
from hogflow.models import BoundingBox, Detection


class FakeCV2(SimpleNamespace):
    COLOR_RGB2BGR = 1
    FONT_HERSHEY_SIMPLEX = 2
    LINE_AA = 3

    def __init__(self, key: int = -1, *, fail: bool = False) -> None:
        super().__init__()
        self.key = key
        self.fail = fail
        self.destroyed: list[str] = []
        self.shown = 0

    @staticmethod
    def cvtColor(frame, _code):
        return frame[..., ::-1]

    @staticmethod
    def rectangle(*_arguments) -> None:
        return None

    @staticmethod
    def putText(*_arguments) -> None:
        return None

    def imshow(self, _name, _canvas) -> None:
        if self.fail:
            raise RuntimeError("display unavailable")
        self.shown += 1

    def waitKey(self, _delay: int) -> int:
        return self.key

    def destroyWindow(self, name: str) -> None:
        self.destroyed.append(name)


def _detections() -> FrameDetections:
    timestamp = datetime(2026, 7, 18, tzinfo=timezone.utc)
    return FrameDetections(
        source_id="camera",
        frame_sequence=0,
        captured_at=timestamp,
        inference_started_at=timestamp,
        inference_completed_at=timestamp,
        frame_width=8,
        frame_height=6,
        detections=(Detection(BoundingBox(1, 1, 4, 4), 0.9, 0, "pig"),),
        model_id="model",
        model_version=None,
        artifact_fingerprint=None,
        inference_duration_ms=2,
    )


def _statistics() -> LiveDetectionStats:
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


def test_preview_is_ephemeral_and_q_requests_stop() -> None:
    cv2 = FakeCV2(ord("q"))
    preview = OpenCVDetectionPreview(cv2_module=cv2, numpy_module=np)

    action = preview.show(frame_packet(0), _detections(), _statistics())
    preview.close()

    assert action is PreviewAction.STOP
    assert cv2.shown == 1
    assert cv2.destroyed == ["HogFlow live detection"]


def test_preview_failure_is_sanitized() -> None:
    preview = OpenCVDetectionPreview(
        cv2_module=FakeCV2(fail=True),
        numpy_module=np,
    )

    with pytest.raises(DetectionPreviewError, match="preview failed"):
        preview.show(frame_packet(0), _detections(), _statistics())
