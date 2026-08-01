from __future__ import annotations

from dataclasses import replace

import pytest
from _phase9_3_helpers import (
    RecordingSource,
    ScriptedCrossingProcessor,
    finite_events,
    source_configuration,
    wait_for_status,
)

from hogflow.bootstrap import build_operator_runtime
from hogflow.camera import CountingPipelineStatus, PreviewHealthState
from hogflow.detection import TemporaryInferenceError
from hogflow.tracking import TemporaryTrackingError


def test_pipeline_separates_detector_and_tracker_failures_and_records_latency() -> None:
    class TemporaryStageProcessor(ScriptedCrossingProcessor):
        def process(self, frame, crossing_lifecycle_id):
            if frame.sequence_number == 0:
                raise TemporaryInferenceError("synthetic detector failure")
            if frame.sequence_number == 1:
                raise TemporaryTrackingError("synthetic tracker failure")
            return super().process(frame, crossing_lifecycle_id)

    source = RecordingSource(events=finite_events(3))
    runtime = build_operator_runtime(
        source_factory=lambda _configuration: source,
        processor_factory=TemporaryStageProcessor,
    )
    runtime.counting_pipeline.configure(source_configuration())

    runtime.counting_pipeline.start()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    snapshot = runtime.counting_pipeline.snapshot()

    assert snapshot.frames_processed == 3
    assert snapshot.temporary_processing_failures == 2
    assert snapshot.detector_failures == 1
    assert snapshot.tracker_failures == 1
    assert snapshot.consecutive_detector_failures == 0
    assert snapshot.processing_samples == 3
    assert snapshot.last_processed_frame_index == 2
    assert snapshot.maximum_processing_latency_ms >= snapshot.average_processing_latency_ms

    with pytest.raises(ValueError, match="cannot exceed"):
        replace(snapshot, last_processed_frame_index=3)


def test_controller_restart_recreates_only_the_existing_one_worker_composition() -> None:
    sources: list[RecordingSource] = []
    processors: list[ScriptedCrossingProcessor] = []

    def source_factory(_configuration):
        source = RecordingSource(events=finite_events(1))
        sources.append(source)
        return source

    def processor_factory():
        processor = ScriptedCrossingProcessor()
        processors.append(processor)
        return processor

    runtime = build_operator_runtime(
        source_factory=source_factory,
        processor_factory=processor_factory,
    )
    runtime.counting_pipeline.configure(source_configuration())
    runtime.counting_pipeline.start()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    runtime.counting_pipeline.restart()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    assert len(sources) == 2
    assert len(processors) == 2
    assert all(source.open_calls == source.close_calls == 1 for source in sources)
    assert all(processor.started == processor.closed == 1 for processor in processors)
    assert not runtime.counting_pipeline.snapshot().worker_alive


def test_preview_restart_recovers_visual_state_without_restarting_pipeline() -> None:
    runtime = build_operator_runtime()
    failed = runtime.counting_pipeline.record_preview_render_failure()

    recovered = runtime.counting_pipeline.restart_preview()

    assert failed.health_state is PreviewHealthState.FAILED
    assert recovered.health_state is PreviewHealthState.WAITING
    assert recovered.render_failures == 0
    assert runtime.counting_pipeline.snapshot().frames_processed == 0
