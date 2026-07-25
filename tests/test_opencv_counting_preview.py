from types import SimpleNamespace

import numpy as np
import pytest
from _phase5_2_helpers import frame_packet
from _phase5_3_helpers import frame_detections
from _phase5_4_helpers import tracked_object, tracking_result

from hogflow.adapters.opencv_counting_preview import OpenCVCountingPreview
from hogflow.counting import (
    CountingPreviewError,
    LifecycleDirectionalCounter,
    LiveCountingConfiguration,
    LiveCrossingConfiguration,
    LiveCrossingDirection,
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

    def __init__(self, *, fail: bool = False) -> None:
        super().__init__()
        self.fail = fail
        self.labels: list[str] = []
        self.destroyed: list[str] = []

    @staticmethod
    def cvtColor(frame, _code):
        return frame[..., ::-1]

    @staticmethod
    def rectangle(*_arguments) -> None:
        return None

    @staticmethod
    def line(*_arguments) -> None:
        return None

    @staticmethod
    def circle(*_arguments) -> None:
        return None

    def putText(self, _canvas, text, *_arguments) -> None:
        self.labels.append(text)

    def imshow(self, _name, _canvas) -> None:
        if self.fail:
            raise RuntimeError("display unavailable")

    @staticmethod
    def waitKey(_delay: int) -> int:
        return -1

    def destroyWindow(self, name: str) -> None:
        self.destroyed.append(name)


def _crossing_configuration() -> LiveCrossingConfiguration:
    return LiveCrossingConfiguration(
        enabled=True,
        line=NormalizedLine(NormalizedPoint(0, 0.5), NormalizedPoint(1, 0.5)),
    )


def _detection_statistics() -> LiveDetectionStats:
    return LiveDetectionStats(
        frames_acquired=2,
        frames_submitted=2,
        frames_inferred=2,
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


def _preview_inputs():
    crossing_configuration = _crossing_configuration()
    counting_configuration = LiveCountingConfiguration(
        enabled=True,
        positive_direction=LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
        crossing_configuration_fingerprint=crossing_configuration.fingerprint,
    )
    crossing_detector = VirtualLineCrossingDetector(crossing_configuration)
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
    counter = LifecycleDirectionalCounter(counting_configuration)
    counter.start("camera", crossing.tracker_lifecycle_id)
    counting = counter.update(crossing)
    return (
        crossing_configuration,
        counting_configuration,
        crossing_detector,
        second,
        crossing,
        counter,
        counting,
    )


def test_counting_preview_labels_lifecycle_count_and_decision() -> None:
    (
        crossing_configuration,
        counting_configuration,
        crossing_detector,
        tracking,
        crossing,
        counter,
        counting,
    ) = _preview_inputs()
    cv2 = FakeCV2()
    preview = OpenCVCountingPreview(
        crossing_configuration,
        counting_configuration,
        cv2_module=cv2,
        numpy_module=np,
    )

    action = preview.show_counting(
        frame_packet(1),
        frame_detections(1),
        tracking,
        crossing,
        counting,
        _detection_statistics(),
        LiveTrackingTelemetry().snapshot(),
        crossing_detector.statistics(),
        counter.statistics(),
    )
    preview.close()

    assert action is PreviewAction.CONTINUE
    assert any(label == "Lifecycle count=1" for label in cv2.labels)
    assert any("decision=counted_positive" in label for label in cv2.labels)
    assert all("verified pigs" not in label.lower() for label in cv2.labels)
    assert cv2.destroyed == ["HogFlow live lifecycle counting"]


def test_counting_preview_failure_is_sanitized() -> None:
    (
        crossing_configuration,
        counting_configuration,
        crossing_detector,
        tracking,
        crossing,
        counter,
        counting,
    ) = _preview_inputs()
    preview = OpenCVCountingPreview(
        crossing_configuration,
        counting_configuration,
        cv2_module=FakeCV2(fail=True),
        numpy_module=np,
    )

    with pytest.raises(CountingPreviewError, match="preview failed"):
        preview.show_counting(
            frame_packet(1),
            frame_detections(1),
            tracking,
            crossing,
            counting,
            _detection_statistics(),
            LiveTrackingTelemetry().snapshot(),
            crossing_detector.statistics(),
            counter.statistics(),
        )
