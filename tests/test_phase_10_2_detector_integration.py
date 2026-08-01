from __future__ import annotations

from pathlib import Path

import pytest
from _phase5_4_helpers import tracked_object
from _phase9_3_helpers import RecordingSource, finite_events, source_configuration, wait_for_status

import hogflow.__main__ as operator_main
from hogflow.application import VideoSourceRequest
from hogflow.bootstrap import DEFAULT_CAMERA_CROSSING_CONFIGURATION, build_operator_runtime
from hogflow.camera import CountingPipelineStatus, DetectorTrackingCrossingProcessor
from hogflow.counting import VirtualLineCrossingDetector
from hogflow.detection import (
    DetectorBackend,
    FailingDetector,
    PigDetectorConfiguration,
    ScriptedDetector,
)
from hogflow.models import BoundingBox, Detection
from hogflow.runtime import RuntimeIssueCategory
from hogflow.tracking import ScriptedTracker


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / "local-pig.pt"
    path.write_bytes(b"synthetic model placeholder")
    return path


def _processor(
    configuration: PigDetectorConfiguration, detector
) -> DetectorTrackingCrossingProcessor:
    tracker = ScriptedTracker(
        {0: (tracked_object(1, 1, 1, 4, 5),)},
    )
    return DetectorTrackingCrossingProcessor(
        detector,
        tracker,
        lambda lifecycle_id: VirtualLineCrossingDetector(
            DEFAULT_CAMERA_CROSSING_CONFIGURATION,
            lifecycle_id_factory=lambda _generation: lifecycle_id,
        ),
        detector_configuration=configuration,
    )


def test_explicit_empty_detector_composition_remains_the_safe_default() -> None:
    runtime = build_operator_runtime()

    snapshot = runtime.counting_pipeline.snapshot().detector

    assert snapshot.backend is DetectorBackend.EMPTY
    assert not snapshot.configured
    assert not snapshot.model_loaded
    assert snapshot.model_identity == "empty-detector"


def test_configured_detector_reaches_serial_tracking_processor_and_metrics(
    tmp_path: Path,
) -> None:
    configuration = PigDetectorConfiguration.ultralytics(
        _artifact(tmp_path),
        target_class_ids=(0,),
    )
    detection = Detection(BoundingBox(1, 1, 4, 5), 0.9, 0, "pig")
    detector = ScriptedDetector({0: (detection,)})
    source = RecordingSource(events=finite_events(1))
    runtime = build_operator_runtime(
        source_factory=lambda _configuration: source,
        processor_factory=lambda: _processor(configuration, detector),
        detector_configuration=configuration,
    )
    runtime.counting_pipeline.configure(source_configuration())

    runtime.counting_pipeline.start()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    snapshot = runtime.counting_pipeline.snapshot()

    assert snapshot.frames_processed == 1
    assert snapshot.detector.backend is DetectorBackend.ULTRALYTICS
    assert snapshot.detector.inference_count == 1
    assert snapshot.detector.successful_inference_count == 1
    assert snapshot.detector.detections_produced == 1
    assert snapshot.detector.frames_with_detections == 1
    assert snapshot.detector.closed
    assert runtime.coordinator.snapshot().aggregate_completed_pig_count == 0


def test_detector_failure_produces_no_counting_evidence_and_feeds_runtime_health(
    tmp_path: Path,
) -> None:
    configuration = PigDetectorConfiguration.ultralytics(_artifact(tmp_path))
    source = RecordingSource(events=finite_events(1))
    detectors: list[FailingDetector] = []

    def processor_factory() -> DetectorTrackingCrossingProcessor:
        detector = FailingDetector(temporary_sequences=(0,))
        detectors.append(detector)
        return _processor(configuration, detector)

    runtime = build_operator_runtime(
        source_factory=lambda _configuration: source,
        processor_factory=processor_factory,
        detector_configuration=configuration,
    )
    runtime.counting_pipeline.configure(source_configuration())

    runtime.counting_pipeline.start()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    pipeline = runtime.counting_pipeline.snapshot()
    heartbeat = runtime.runtime_supervisor.heartbeat()

    assert pipeline.detector.inference_count == 1
    assert pipeline.detector.temporary_failures == 1
    assert pipeline.detector.successful_inference_count == 0
    assert pipeline.detector_failures == 1
    assert heartbeat.diagnostics.detector_failures == 1
    assert any(
        issue.category is RuntimeIssueCategory.DETECTOR_FAILURE
        for issue in heartbeat.current_issues
    )
    assert runtime.coordinator.snapshot().aggregate_completed_pig_count == 0


def test_restart_creates_one_fresh_detector_lifecycle_without_per_frame_reload(
    tmp_path: Path,
) -> None:
    configuration = PigDetectorConfiguration.ultralytics(_artifact(tmp_path))
    sources: list[RecordingSource] = []
    detectors: list[ScriptedDetector] = []

    def source_factory(_configuration):
        source = RecordingSource(events=finite_events(2))
        sources.append(source)
        return source

    def processor_factory() -> DetectorTrackingCrossingProcessor:
        detector = ScriptedDetector({})
        detectors.append(detector)
        return _processor(configuration, detector)

    runtime = build_operator_runtime(
        source_factory=source_factory,
        processor_factory=processor_factory,
        detector_configuration=configuration,
    )
    runtime.counting_pipeline.configure(source_configuration())
    runtime.counting_pipeline.start()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    runtime.counting_pipeline.restart()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    assert len(detectors) == 2
    assert all(detector.inferred_sequences == [0, 1] for detector in detectors)
    assert all(not detector.is_loaded for detector in detectors)
    assert len(sources) == 2


def test_local_file_replay_reuses_the_loaded_detector_lifecycle(tmp_path: Path) -> None:
    configuration = PigDetectorConfiguration.ultralytics(_artifact(tmp_path))
    video = tmp_path / "synthetic-replay.mp4"
    video.write_bytes(b"synthetic-test-only")
    sources: list[RecordingSource] = []
    detectors: list[ScriptedDetector] = []

    def source_factory(_configuration):
        source = RecordingSource(events=finite_events(2))
        sources.append(source)
        return source

    def processor_factory() -> DetectorTrackingCrossingProcessor:
        detector = ScriptedDetector({})
        detectors.append(detector)
        return _processor(configuration, detector)

    runtime = build_operator_runtime(
        source_factory=source_factory,
        processor_factory=processor_factory,
        detector_configuration=configuration,
    )
    runtime.application.configure_video_source(VideoSourceRequest.video_file(video))

    runtime.application.start_counting_pipeline()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    runtime.application.restart_video()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    assert len(detectors) == 1
    assert detectors[0].is_loaded
    assert detectors[0].inferred_sequences == [0, 1, 2, 3]
    assert len(sources) == 2

    runtime.application.shutdown()
    assert not detectors[0].is_loaded


def test_operator_cli_passes_validated_detector_configuration_without_path_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = _artifact(tmp_path)
    captured: list[PigDetectorConfiguration] = []

    class Composition:
        def run(self) -> None:
            pass

    def compose(**settings):
        captured.append(settings["detector_configuration"])
        return Composition()

    monkeypatch.setattr(operator_main, "compose_operator_desktop", compose)

    assert (
        operator_main.main(
            [
                "run",
                "--detector",
                "ultralytics",
                "--model-path",
                str(artifact),
                "--target-class-id",
                "0",
                "--confidence-threshold",
                "0.6",
                "--device",
                "cpu",
            ]
        )
        == 0
    )
    assert captured[0].confidence_threshold == 0.6
    assert captured[0].target_class_ids == (0,)
    assert str(tmp_path) not in repr(captured[0])


def test_operator_cli_rejects_invalid_detector_before_composition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        operator_main,
        "compose_operator_desktop",
        lambda **_settings: pytest.fail("Invalid detector must fail before composition."),
    )

    with pytest.raises(SystemExit) as missing:
        operator_main.main(["run", "--detector", "ultralytics"])
    with pytest.raises(SystemExit) as conflicting:
        operator_main.main(["run", "--model-path", str(_artifact(tmp_path))])

    assert missing.value.code == 2
    assert conflicting.value.code == 2
