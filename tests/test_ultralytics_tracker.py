import numpy as np
import pytest

from hogflow.adapters import ultralytics_tracker as tracker_module
from hogflow.adapters.ultralytics_tracker import UltralyticsTracker
from hogflow.models import BoundingBox, Detection, Frame, Track


class _FakeTrackerBackend:
    def __init__(self) -> None:
        self.calls = 0
        self.received: list[object] = []

    def update(self, detections: object) -> np.ndarray:
        self.calls += 1
        self.received.append(detections)
        if len(detections) == 0:  # type: ignore[arg-type]
            return np.empty((0, 8), dtype=float)
        return np.asarray([[2, 3, 8, 11, 7, 0.85, 0, 0]], dtype=float)


def _frame(index: int = 0) -> Frame:
    return Frame(index, 12, 12, bytes(12 * 12 * 3), float(index))


def _detection() -> Detection:
    return Detection(BoundingBox(1, 2, 9, 10), 0.9, 0, "person")


@pytest.fixture
def fake_backend(monkeypatch: pytest.MonkeyPatch) -> _FakeTrackerBackend:
    backend = _FakeTrackerBackend()
    monkeypatch.setattr(
        tracker_module,
        "_load_tracker_runtime",
        lambda _configuration: (np, backend),
    )
    return backend


def test_tracker_preserves_ids_and_converts_bounding_boxes(
    fake_backend: _FakeTrackerBackend,
) -> None:
    tracker = UltralyticsTracker()

    result = tracker.update(_frame(), (_detection(),))

    assert result == (Track(7, Detection(BoundingBox(2.0, 3.0, 8.0, 11.0), 0.85, 0, "person")),)
    assert isinstance(result, tuple)


def test_tracker_passes_external_detections_to_backend(fake_backend: _FakeTrackerBackend) -> None:
    tracker = UltralyticsTracker()

    tracker.update(_frame(), (_detection(),))

    private_result = fake_backend.received[0]
    assert private_result.conf.tolist() == pytest.approx([0.9])  # type: ignore[attr-defined]
    assert private_result.xywh[0].tolist() == pytest.approx([5.0, 6.0, 8.0, 8.0])  # type: ignore[attr-defined]


def test_tracker_backend_state_is_reused_across_frames(fake_backend: _FakeTrackerBackend) -> None:
    tracker = UltralyticsTracker()

    first = tracker.update(_frame(0), (_detection(),))
    second = tracker.update(_frame(1), (_detection(),))

    assert fake_backend.calls == 2
    assert first[0].tracker_id == second[0].tracker_id == 7


def test_tracker_returns_empty_immutable_tuple_for_no_tracks(
    fake_backend: _FakeTrackerBackend,
) -> None:
    tracker = UltralyticsTracker()

    assert tracker.update(_frame(), ()) == ()


def test_framework_result_objects_do_not_escape(fake_backend: _FakeTrackerBackend) -> None:
    tracker = UltralyticsTracker()

    result = tracker.update(_frame(), (_detection(),))

    assert all(isinstance(item, Track) for item in result)
    assert not any(isinstance(item, np.ndarray) for item in result)
