from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pytest
from _phase5_3_helpers import pig_detection, tracking_request

import hogflow.adapters.supervision_bytetrack as adapter_module
from hogflow.adapters.supervision_bytetrack import SupervisionByteTrackAdapter
from hogflow.tracking import (
    ByteTrackConfiguration,
    MalformedTrackerOutputError,
    StaleTrackingRequestError,
    TrackerLifecycleError,
)


class FakeDetections:
    def __init__(self, *, xyxy, confidence, class_id, data=None, tracker_id=None) -> None:
        self.xyxy = xyxy
        self.confidence = confidence
        self.class_id = class_id
        self.data = {} if data is None else data
        self.tracker_id = tracker_id

    def __len__(self) -> int:
        return len(self.xyxy)


@dataclass
class FakeBackend:
    settings: dict[str, object]
    reset_calls: int = 0

    def update_with_detections(self, detections: FakeDetections) -> FakeDetections:
        detections.tracker_id = np.arange(len(detections), dtype=int) + 10
        return detections

    def reset(self) -> None:
        self.reset_calls += 1


class FakeBackendFactory:
    instances: list[FakeBackend] = []

    def __new__(cls, **settings):
        backend = FakeBackend(settings)
        cls.instances.append(backend)
        return backend


def _runtime(monkeypatch, backend_type=FakeBackendFactory) -> None:
    FakeBackendFactory.instances.clear()
    monkeypatch.setattr(
        adapter_module,
        "_load_runtime",
        lambda: (np, FakeDetections, backend_type, "0.29.1"),
    )


def test_adapter_uses_verified_supervision_configuration_and_converts_results(monkeypatch) -> None:
    _runtime(monkeypatch)
    configuration = ByteTrackConfiguration(
        track_activation_threshold=0.2,
        lost_track_buffer=4,
        minimum_matching_threshold=0.7,
        frame_rate=15,
        minimum_consecutive_frames=2,
    )
    tracker = SupervisionByteTrackAdapter(configuration)
    tracker.start("camera")
    request = tracking_request(
        0,
        (
            pig_detection(1, 1, 4, 4, confidence=0.8),
            pig_detection(8, 1, 12, 5, confidence=0.9),
        ),
    )

    result = tracker.update(request)

    assert FakeBackendFactory.instances[0].settings == {
        "track_activation_threshold": 0.2,
        "lost_track_buffer": 4,
        "minimum_matching_threshold": 0.7,
        "frame_rate": 15,
        "minimum_consecutive_frames": 2,
    }
    assert [item.track.tracker_id for item in result.tracked_objects] == [10, 11]
    assert [item.source_detection_index for item in result.tracked_objects] == [0, 1]
    assert result.tracked_objects[0].track.detection.class_name == "pig"
    assert isinstance(result.tracked_objects, tuple)
    assert result.tracker_version == "0.29.1"


def test_adapter_handles_zero_detections_reset_and_idempotent_close(monkeypatch) -> None:
    _runtime(monkeypatch)
    tracker = SupervisionByteTrackAdapter()
    tracker.start("camera")

    assert tracker.update(tracking_request(0)).tracked_objects == ()
    tracker.reset()
    tracker.close()
    tracker.close()

    assert FakeBackendFactory.instances[0].reset_calls == 2
    assert not tracker.is_started


def test_adapter_rejects_stale_and_cross_stream_requests(monkeypatch) -> None:
    _runtime(monkeypatch)
    tracker = SupervisionByteTrackAdapter()
    tracker.start("camera")
    tracker.update(tracking_request(1))

    with pytest.raises(StaleTrackingRequestError):
        tracker.update(tracking_request(1))
    with pytest.raises(TrackerLifecycleError, match="mix"):
        tracker.update(tracking_request(2, source_id="other"))


@pytest.mark.parametrize(
    "field,value",
    (
        ("tracker_id", np.asarray([float("nan")])),
        ("confidence", np.asarray([float("inf")])),
        ("class_id", np.asarray([-1])),
        ("xyxy", np.asarray([[3.0, 3.0, 3.0, 4.0]])),
    ),
)
def test_adapter_rejects_invalid_framework_output(monkeypatch, field, value) -> None:
    class InvalidBackend(FakeBackend):
        def __init__(self, **settings) -> None:
            super().__init__(settings)

        def update_with_detections(self, detections):
            detections.tracker_id = np.asarray([1])
            setattr(detections, field, value)
            return detections

    _runtime(monkeypatch, InvalidBackend)
    tracker = SupervisionByteTrackAdapter()
    tracker.start("camera")

    with pytest.raises(MalformedTrackerOutputError):
        tracker.update(tracking_request(0, (pig_detection(),)))


def test_adapter_clips_valid_framework_box_to_frame(monkeypatch) -> None:
    class ClippingBackend(FakeBackend):
        def __init__(self, **settings) -> None:
            super().__init__(settings)

        def update_with_detections(self, detections):
            detections.tracker_id = np.asarray([1])
            detections.xyxy = np.asarray([[-2.0, -1.0, 25.0, 15.0]])
            return detections

    _runtime(monkeypatch, ClippingBackend)
    tracker = SupervisionByteTrackAdapter()
    tracker.start("camera")

    result = tracker.update(tracking_request(0, (pig_detection(),)))

    box = result.tracked_objects[0].track.detection.bounding_box
    assert (box.x_min, box.y_min, box.x_max, box.y_max) == (0.0, 0.0, 20.0, 12.0)


def test_installed_supervision_exposes_the_supported_bytetrack_api() -> None:
    from supervision.tracker.byte_tracker.core import ByteTrack

    assert callable(ByteTrack)
    assert callable(getattr(ByteTrack, "update_with_detections"))
    assert callable(getattr(ByteTrack, "reset"))


def test_no_framework_types_escape_adapter(monkeypatch) -> None:
    _runtime(monkeypatch)
    tracker = SupervisionByteTrackAdapter()
    tracker.start("camera")

    result = tracker.update(tracking_request(0, (pig_detection(),)))

    assert result.__class__.__module__.startswith("hogflow.")
    assert result.tracked_objects[0].__class__.__module__.startswith("hogflow.")
    assert not isinstance(result, (np.ndarray, SimpleNamespace, FakeDetections))
