from types import SimpleNamespace

import numpy as np
import pytest

from hogflow.adapters import ultralytics_detector as detector_module
from hogflow.adapters.ultralytics_detector import UltralyticsDetector
from hogflow.core import ConfigurationError
from hogflow.models import BoundingBox, Detection, Frame


class _FakeCV2:
    COLOR_RGB2BGR = 1

    @staticmethod
    def cvtColor(frame: np.ndarray, _conversion: int) -> np.ndarray:
        return frame[..., ::-1]


class _FakeBoxes:
    def __init__(
        self, xyxy: list[list[float]], confidence: list[float], classes: list[int]
    ) -> None:
        self.xyxy = np.asarray(xyxy, dtype=float)
        self.conf = np.asarray(confidence, dtype=float)
        self.cls = np.asarray(classes, dtype=float)

    def __len__(self) -> int:
        return len(self.conf)


class _FakeModel:
    names = {0: "person", 2: "car"}
    boxes = _FakeBoxes([[1, 2, 5, 8]], [0.9], [0])
    last_arguments: dict[str, object] | None = None

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def predict(self, **arguments: object) -> list[SimpleNamespace]:
        type(self).last_arguments = arguments
        return [SimpleNamespace(boxes=type(self).boxes)]


def _frame() -> Frame:
    return Frame(
        frame_index=0,
        width=2,
        height=1,
        pixels=bytes([10, 20, 30, 40, 50, 60]),
        timestamp_seconds=0.0,
    )


@pytest.fixture(autouse=True)
def fake_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeModel.boxes = _FakeBoxes([[1, 2, 5, 8]], [0.9], [0])
    _FakeModel.last_arguments = None
    monkeypatch.setattr(
        detector_module,
        "_load_runtime",
        lambda: (_FakeCV2, np, _FakeModel),
    )


def test_detector_converts_framework_results_to_immutable_detections() -> None:
    detector = UltralyticsDetector("generic.pt", "person", 0.35, device="cpu")

    result = detector.predict(_frame())

    assert result == (Detection(BoundingBox(1.0, 2.0, 5.0, 8.0), 0.9, 0, "person"),)
    assert isinstance(result, tuple)
    assert _FakeModel.last_arguments is not None
    assert _FakeModel.last_arguments["classes"] == [0]
    assert _FakeModel.last_arguments["conf"] == 0.35
    assert _FakeModel.last_arguments["device"] == "cpu"
    source = _FakeModel.last_arguments["source"]
    assert isinstance(source, np.ndarray)
    assert source[0, 0].tolist() == [30, 20, 10]


def test_detector_defensively_filters_wrong_classes() -> None:
    _FakeModel.boxes = _FakeBoxes([[1, 2, 5, 8], [2, 2, 6, 8]], [0.9, 0.8], [0, 2])
    detector = UltralyticsDetector("generic.pt", "person", 0.35)

    result = detector.predict(_frame())

    assert len(result) == 1
    assert result[0].class_name == "person"


def test_detector_defensively_filters_low_confidence() -> None:
    _FakeModel.boxes = _FakeBoxes([[1, 2, 5, 8]], [0.2], [0])
    detector = UltralyticsDetector("generic.pt", "person", 0.35)

    assert detector.predict(_frame()) == ()


def test_unknown_class_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="Available classes"):
        UltralyticsDetector("generic.pt", "unknown-class", 0.35)


@pytest.mark.parametrize("confidence", [0.0, -0.1, 1.1, True])
def test_invalid_confidence_is_rejected(confidence: object) -> None:
    with pytest.raises(ConfigurationError, match="Confidence"):
        UltralyticsDetector("generic.pt", "person", confidence)  # type: ignore[arg-type]


def test_framework_result_objects_do_not_escape() -> None:
    detector = UltralyticsDetector("generic.pt", "person", 0.35)

    result = detector.predict(_frame())

    assert all(isinstance(item, Detection) for item in result)
    assert not any(isinstance(item, _FakeBoxes) for item in result)
