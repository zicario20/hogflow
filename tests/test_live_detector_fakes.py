from time import monotonic

import pytest
from _phase5_2_helpers import frame_packet

from hogflow.detection import EmptyDetector, FailingDetector, ScriptedDetector, SlowDetector
from hogflow.detection.errors import (
    DetectorLifecycleError,
    FatalInferenceError,
    TemporaryInferenceError,
)
from hogflow.models import BoundingBox, Detection


def test_empty_and_scripted_detectors_have_explicit_lifecycle() -> None:
    frame = frame_packet(2)
    detection = Detection(BoundingBox(1, 1, 4, 4), 0.8, 0, "pig")
    detector = ScriptedDetector({2: (detection,)})

    with pytest.raises(DetectorLifecycleError):
        detector.infer(frame)
    detector.load()
    result = detector.infer(frame)
    detector.close()

    assert result.frame_sequence == 2
    assert result.detections == (detection,)
    assert not detector.is_loaded
    assert EmptyDetector().metadata.framework == "synthetic"


def test_slow_detector_uses_injected_delay_without_frameworks() -> None:
    delays: list[float] = []
    detector = SlowDetector(delay_seconds=0.25, sleeper=delays.append)
    detector.load()

    result = detector.infer(frame_packet(0, monotonic_seconds=monotonic()))

    assert result.detections == ()
    assert delays == [0.25]


def test_failing_detector_distinguishes_temporary_and_fatal_failures() -> None:
    detector = FailingDetector(temporary_sequences=(1,), fatal_sequences=(2,))
    detector.load()

    with pytest.raises(TemporaryInferenceError):
        detector.infer(frame_packet(1))
    with pytest.raises(FatalInferenceError):
        detector.infer(frame_packet(2))
