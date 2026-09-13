from __future__ import annotations

from datetime import datetime, timezone

from hogflow.calibration import (
    AutonomousCalibrationSettings,
    AutonomousDemoConfiguration,
    CalibrationStatus,
    run_autonomous_demo,
)
from hogflow.calibration.models import DirectionVector, LineCandidate
from hogflow.calibration.orchestration import _shift_candidate
from hogflow.counting import LiveCrossingDirection, NormalizedLine, NormalizedPoint
from hogflow.detection import DetectorBackend, PigDetectorConfiguration
from hogflow.detection.inference import FrameDetections, ModelArtifactMetadata
from hogflow.models import BoundingBox, Detection, Track
from hogflow.streaming import FrameDimensions, StreamConfiguration
from hogflow.streaming.synthetic import SyntheticCameraSource
from hogflow.tracking import ByteTrackConfiguration
from hogflow.tracking.models import TrackedObject, TrackingResult

_NOW = datetime(2026, 9, 13, tzinfo=timezone.utc)
_SHA = "0" * 64


def _configuration() -> AutonomousDemoConfiguration:
    return AutonomousDemoConfiguration(
        demo_id="synthetic_demo",
        detector_configuration=PigDetectorConfiguration(
            backend=DetectorBackend.EMPTY,
            target_class_name="pig",
        ),
        tracker_configuration=ByteTrackConfiguration(),
        calibration_settings=AutonomousCalibrationSettings(
            minimum_lifetime_frames=4,
            minimum_displacement=0.10,
            minimum_continuity_ratio=0.75,
            minimum_direction_resultant=0.20,
            candidate_positions=(0.40, 0.50, 0.60),
        ),
    )


def _source_factory(_configuration: StreamConfiguration) -> SyntheticCameraSource:
    return SyntheticCameraSource(
        stream_id="synthetic_demo",
        frame_count=12,
        dimensions=FrameDimensions(100, 100, 3),
    )


class _Detector:
    def __init__(self) -> None:
        self._loaded = False
        self._metadata = ModelArtifactMetadata(
            model_id="synthetic-model",
            framework="synthetic",
            class_mapping=((0, "pig"),),
            artifact_fingerprint=_SHA,
        )

    @property
    def metadata(self) -> ModelArtifactMetadata:
        return self._metadata

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def load(self) -> None:
        self._loaded = True

    def infer(self, frame):
        detections = []
        for track_id in range(3):
            x = 20 + track_id * 25
            y = 10 + frame.sequence_number * 7
            detections.append(
                Detection(
                    bounding_box=BoundingBox(x - 3, y - 3, x + 3, y + 3),
                    confidence=0.9,
                    class_id=0,
                    class_name="pig",
                )
            )
        return FrameDetections(
            source_id=frame.stream.stream_id,
            frame_sequence=frame.sequence_number,
            captured_at=frame.timestamp.acquired_at,
            inference_started_at=frame.timestamp.acquired_at,
            inference_completed_at=frame.timestamp.acquired_at,
            frame_width=frame.dimensions.width,
            frame_height=frame.dimensions.height,
            detections=tuple(detections),
            model_id="synthetic-model",
            model_version=None,
            artifact_fingerprint=_SHA,
            inference_duration_ms=0.0,
        )

    def close(self) -> None:
        self._loaded = False


class _Tracker:
    reset_calls = 0

    def __init__(self) -> None:
        self._started = False
        self._stream_id = None

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def metadata(self):
        return type(
            "Metadata",
            (),
            {"configuration_fingerprint": _SHA},
        )()

    def start(self, stream_id: str) -> None:
        self._started = True
        self._stream_id = stream_id

    def update(self, request):
        return TrackingResult(
            source_id=request.source_id,
            frame_sequence=request.frame_sequence,
            captured_at=request.captured_at,
            frame_width=request.frame_width,
            frame_height=request.frame_height,
            tracked_objects=tuple(
                TrackedObject(Track(index, detection))
                for index, detection in enumerate(request.detections)
            ),
            tracker_id="synthetic-tracker",
            tracker_version="1",
            configuration_fingerprint=_SHA,
            processing_started_at=request.captured_at,
            processing_finished_at=request.captured_at,
            tracking_latency_ms=0.0,
        )

    def reset(self) -> None:
        type(self).reset_calls += 1

    def close(self) -> None:
        self._started = False


def _detector_factory(_configuration: PigDetectorConfiguration) -> _Detector:
    return _Detector()


def _tracker_factory(_configuration: ByteTrackConfiguration) -> _Tracker:
    return _Tracker()


def test_calibration_does_not_leak_into_second_pass_count() -> None:
    _Tracker.reset_calls = 0
    result = run_autonomous_demo(
        _configuration(),
        source_factory=_source_factory,
        detector_factory=_detector_factory,
        tracker_factory=_tracker_factory,
        clock=lambda: _NOW,
    )

    assert result.calibration.status is CalibrationStatus.READY
    assert result.calibration_crossing_events == 0
    assert result.pass_two_first_frame_sequence == 0
    assert result.primary_count == 3
    assert _Tracker.reset_calls >= 1


def test_inconclusive_calibration_never_starts_counting() -> None:
    configuration = _configuration()
    configuration = AutonomousDemoConfiguration(
        demo_id=configuration.demo_id,
        detector_configuration=configuration.detector_configuration,
        tracker_configuration=configuration.tracker_configuration,
        calibration_settings=AutonomousCalibrationSettings(minimum_lifetime_frames=100),
    )
    result = run_autonomous_demo(
        configuration,
        source_factory=_source_factory,
        detector_factory=_detector_factory,
        tracker_factory=_tracker_factory,
        clock=lambda: _NOW,
    )

    assert result.calibration.status is CalibrationStatus.INCONCLUSIVE
    assert result.primary_count is None
    assert result.pass_two_first_frame_sequence is None


def test_neighbor_line_outside_image_is_marked_unavailable() -> None:
    candidate = LineCandidate(
        candidate_id="line_01",
        line=NormalizedLine(NormalizedPoint(0.01, 0.2), NormalizedPoint(0.01, 0.8)),
        along_position=0.5,
        positive_direction=LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
        edge_penalty=0.8,
    )

    assert _shift_candidate(candidate, DirectionVector(1.0, 0.0), -0.1, "n") is None


def test_runtime_failure_is_reported_as_a_sanitized_category() -> None:
    def failing_detector(_configuration):
        raise RuntimeError("private local details")

    result = run_autonomous_demo(
        _configuration(),
        source_factory=_source_factory,
        detector_factory=failing_detector,
        tracker_factory=_tracker_factory,
        clock=lambda: _NOW,
    )

    assert result.calibration.status is CalibrationStatus.FAILED
    assert result.failures == ("bounded_runtime_failure", "runtime_exception_RuntimeError")
    assert "private" not in str(result)
