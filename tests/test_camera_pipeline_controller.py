from __future__ import annotations

from threading import Event

import pytest
from _phase7_helpers import crossing_result
from _phase9_3_helpers import (
    BlockingSource,
    RecordingSource,
    ScriptedCrossingProcessor,
    fatal_events,
    finite_events,
    source_configuration,
    wait_for_status,
)
from _phase9_helpers import LifecycleIdFactory, StepClock, registration

from hogflow.application import DockId, VideoSourceRequest
from hogflow.bootstrap import DEFAULT_CAMERA_CROSSING_CONFIGURATION, build_operator_runtime
from hogflow.camera import (
    ActiveCountingBinding,
    CameraPipelineLifecycleError,
    CameraStatus,
    CountingPipelineStatus,
    PipelineFailureCategory,
    StaleCameraEvidenceError,
)
from hogflow.counting import CrossingLifecycleError
from hogflow.detection import FatalInferenceError, TemporaryInferenceError
from hogflow.domain import PigType
from hogflow.streaming.errors import StreamOpenError
from hogflow.tracking import FatalTrackingError


def runtime_with(source, processor):
    return build_operator_runtime(
        clock=StepClock(),
        lifecycle_id_factory=LifecycleIdFactory(),
        source_factory=lambda _configuration: source,
        processor_factory=lambda: processor,
    )


def activate_session(runtime, dock_id: DockId = DockId.DOCK_1) -> None:
    application = runtime.application
    application.register_truck(registration(dock_id))
    application.start_truck(dock_id)
    application.start_session(dock_id, f"{dock_id.value}-session-1")


def test_pipeline_configures_starts_exhausts_and_closes_source_once() -> None:
    source = RecordingSource(events=finite_events(2))
    processor = ScriptedCrossingProcessor()
    runtime = runtime_with(source, processor)

    configured = runtime.counting_pipeline.configure(source_configuration())
    started = runtime.counting_pipeline.start()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    ended = runtime.counting_pipeline.snapshot()

    assert configured.camera.status is CameraStatus.CLOSED
    assert started.status in (
        CountingPipelineStatus.RUNNING,
        CountingPipelineStatus.STOPPED,
    )
    assert ended.camera.status is CameraStatus.ENDED
    assert ended.camera.source_exhausted
    assert ended.camera.frames_acquired == 2
    assert ended.frames_processed == 2
    assert source.open_calls == 1
    assert source.close_calls == 1
    assert processor.started == 1
    assert processor.closed == 1


def test_duplicate_start_is_rejected_and_repeated_stop_is_safe() -> None:
    source = BlockingSource()
    processor = ScriptedCrossingProcessor()
    runtime = runtime_with(source, processor)
    runtime.counting_pipeline.configure(source_configuration())
    runtime.counting_pipeline.start()
    assert source.read_entered.wait(1)

    with pytest.raises(CameraPipelineLifecycleError, match="already active"):
        runtime.counting_pipeline.start()

    first = runtime.counting_pipeline.stop()
    second = runtime.counting_pipeline.stop()

    assert first.status is CountingPipelineStatus.STOPPED
    assert second == first
    assert not first.worker_alive
    assert source.open_calls == 1
    assert source.close_calls == 1


def test_fatal_frame_read_failure_is_reported_and_releases_source() -> None:
    source = RecordingSource(events=fatal_events())
    runtime = runtime_with(source, ScriptedCrossingProcessor())
    runtime.counting_pipeline.configure(source_configuration())

    runtime.counting_pipeline.start()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.FAILED)
    snapshot = runtime.counting_pipeline.snapshot()

    assert snapshot.camera.status is CameraStatus.FAILED
    assert snapshot.failure_category is PipelineFailureCategory.SOURCE_READ
    assert snapshot.failure_message == (
        "Configured video source could not continue reading frames."
    )
    assert source.close_calls == 1
    assert not snapshot.worker_alive


def test_unavailable_source_reports_open_failure_without_starting_processor() -> None:
    class UnavailableSource(RecordingSource):
        def open(self) -> None:
            self.open_calls += 1
            raise StreamOpenError("synthetic unavailable camera")

    source = UnavailableSource(events=finite_events(1))
    processor = ScriptedCrossingProcessor()
    runtime = runtime_with(source, processor)
    runtime.counting_pipeline.configure(source_configuration())

    runtime.counting_pipeline.start()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.FAILED)
    snapshot = runtime.counting_pipeline.snapshot()

    assert snapshot.failure_category is PipelineFailureCategory.SOURCE_OPEN
    assert snapshot.failure_message == "Configured video source could not be opened."
    assert processor.started == 0
    assert source.open_calls == 1
    assert source.close_calls == 0


def test_temporary_processing_failure_skips_one_frame_and_worker_continues() -> None:
    class TemporarilyFailingProcessor(ScriptedCrossingProcessor):
        def process(self, frame, crossing_lifecycle_id):
            if frame.sequence_number == 0:
                raise TemporaryInferenceError("synthetic temporary detector failure")
            return super().process(frame, crossing_lifecycle_id)

    source = RecordingSource(events=finite_events(2))
    processor = TemporarilyFailingProcessor()
    runtime = runtime_with(source, processor)
    runtime.counting_pipeline.configure(source_configuration())

    runtime.counting_pipeline.start()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    snapshot = runtime.counting_pipeline.snapshot()

    assert snapshot.frames_processed == 2
    assert snapshot.temporary_processing_failures == 1
    assert processor.processed == [(1, None)]
    assert snapshot.failure_category is PipelineFailureCategory.NONE


@pytest.mark.parametrize(
    ("error", "category"),
    (
        (
            FatalInferenceError("synthetic detector failure"),
            PipelineFailureCategory.DETECTOR,
        ),
        (
            FatalTrackingError("synthetic tracker failure"),
            PipelineFailureCategory.TRACKER,
        ),
        (
            CrossingLifecycleError("synthetic crossing failure"),
            PipelineFailureCategory.CROSSING,
        ),
    ),
)
def test_processing_stage_failures_are_categorized_and_cleanup_is_deterministic(
    error: Exception,
    category: PipelineFailureCategory,
) -> None:
    class FailingProcessor(ScriptedCrossingProcessor):
        def process(self, frame, crossing_lifecycle_id):
            raise error

    source = RecordingSource(events=finite_events(1))
    processor = FailingProcessor()
    runtime = runtime_with(source, processor)
    runtime.counting_pipeline.configure(source_configuration())

    runtime.counting_pipeline.start()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.FAILED)
    snapshot = runtime.counting_pipeline.snapshot()

    assert snapshot.failure_category is category
    assert not snapshot.worker_alive
    assert source.close_calls == 1
    assert processor.closed == 1


def test_frames_without_lane_owner_are_processed_but_never_counted() -> None:
    source = RecordingSource(events=finite_events(3))
    processor = ScriptedCrossingProcessor(event_sequences=(1, 2))
    runtime = runtime_with(source, processor)
    runtime.application.configure_video_source(VideoSourceRequest.camera(0))

    runtime.application.start_counting_pipeline()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    assert runtime.application.snapshot().aggregate_completed_pig_count == 0
    assert all(lifecycle is None for _sequence, lifecycle in processor.processed)


def test_active_session_receives_crossing_event_through_shared_lane() -> None:
    source = RecordingSource(events=finite_events(3))
    processor = ScriptedCrossingProcessor(event_sequences=(1,))
    runtime = runtime_with(source, processor)
    activate_session(runtime)
    lifecycle_id = runtime.application.snapshot().counting_lane.crossing_lifecycle_id
    runtime.application.configure_video_source(VideoSourceRequest.camera(0))

    runtime.application.start_counting_pipeline()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    snapshot = runtime.application.snapshot()

    assert snapshot.counting_lane.current_session_count == 1
    assert any(item == (1, lifecycle_id) for item in processor.processed)
    assert runtime.counter.statistics().positives_counted == 1


def test_wrong_dock_or_lifecycle_binding_is_rejected_without_dock_mutation() -> None:
    runtime = runtime_with(
        RecordingSource(events=finite_events(0)),
        ScriptedCrossingProcessor(),
    )
    activate_session(runtime)
    current = runtime.runtime_access.active_binding()
    assert current is not None
    before = runtime.application.snapshot()
    wrong = ActiveCountingBinding(
        DockId.DOCK_2,
        current.source_id,
        current.crossing_lifecycle_id,
    )
    result = crossing_result(
        1,
        source_id=current.source_id,
        lifecycle_id=current.crossing_lifecycle_id,
        crossing_fingerprint=DEFAULT_CAMERA_CROSSING_CONFIGURATION.fingerprint,
    )

    with pytest.raises(StaleCameraEvidenceError):
        runtime.runtime_access.route_crossing(wrong, result)

    assert runtime.application.snapshot().dock_snapshots == before.dock_snapshots


@pytest.mark.parametrize("terminal_action", ("complete", "cancel"))
def test_delayed_result_after_session_release_is_rejected_as_stale(
    terminal_action: str,
) -> None:
    entered = Event()
    release = Event()
    source = RecordingSource(events=finite_events(2))
    processor = ScriptedCrossingProcessor(
        event_sequences=(1,),
        entered=entered,
        release=release,
    )
    runtime = runtime_with(source, processor)
    activate_session(runtime)
    runtime.application.configure_video_source(VideoSourceRequest.camera(0))
    runtime.application.start_counting_pipeline()
    assert entered.wait(1)

    if terminal_action == "complete":
        runtime.application.complete_session(DockId.DOCK_1)
    else:
        runtime.application.cancel_session(DockId.DOCK_1)
    release.set()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    pipeline = runtime.counting_pipeline.snapshot()
    snapshot = runtime.application.snapshot()
    assert pipeline.stale_results_rejected == 1
    assert not snapshot.counting_lane.occupied
    assert snapshot.for_dock(DockId.DOCK_1).truck_total == 0


def test_previous_session_result_cannot_increment_next_session() -> None:
    entered = Event()
    release = Event()
    source = RecordingSource(events=finite_events(2))
    processor = ScriptedCrossingProcessor(
        event_sequences=(1,),
        entered=entered,
        release=release,
    )
    runtime = runtime_with(source, processor)
    application = runtime.application
    application.register_truck(registration(DockId.DOCK_1, (PigType.REGULAR, PigType.OPG)))
    application.start_truck(DockId.DOCK_1)
    application.start_session(DockId.DOCK_1, "dock_1-session-1")
    application.configure_video_source(VideoSourceRequest.camera(0))
    application.start_counting_pipeline()
    assert entered.wait(1)

    application.complete_session(DockId.DOCK_1)
    application.start_session(DockId.DOCK_1, "dock_1-session-2")
    release.set()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)

    snapshot = application.snapshot()
    assert snapshot.counting_lane.current_session_count == 0
    assert runtime.counting_pipeline.snapshot().stale_results_rejected == 1


def test_one_pipeline_serves_two_docks_sequentially_with_same_tracker_id() -> None:
    sources = [
        RecordingSource(events=finite_events(3)),
        RecordingSource(events=finite_events(3)),
    ]
    processors = [
        ScriptedCrossingProcessor(event_sequences=(1,), tracker_id=42),
        ScriptedCrossingProcessor(event_sequences=(1,), tracker_id=42),
    ]
    runtime = build_operator_runtime(
        clock=StepClock(),
        lifecycle_id_factory=LifecycleIdFactory(),
        source_factory=lambda _configuration: sources.pop(0),
        processor_factory=lambda: processors.pop(0),
    )
    application = runtime.application
    for dock in (DockId.DOCK_1, DockId.DOCK_2):
        application.register_truck(registration(dock))
        application.start_truck(dock)

    application.start_session(DockId.DOCK_1, "dock_1-session-1")
    application.configure_video_source(VideoSourceRequest.camera(0))
    application.start_counting_pipeline()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    application.complete_session(DockId.DOCK_1)

    application.start_session(DockId.DOCK_2, "dock_2-session-1")
    application.configure_video_source(VideoSourceRequest.camera(0))
    application.start_counting_pipeline()
    wait_for_status(runtime.counting_pipeline, CountingPipelineStatus.STOPPED)
    application.complete_session(DockId.DOCK_2)

    snapshot = application.snapshot()
    assert snapshot.for_dock(DockId.DOCK_1).truck_total == 1
    assert snapshot.for_dock(DockId.DOCK_2).truck_total == 1
    assert snapshot.aggregate_completed_pig_count == 2


def test_application_shutdown_stops_worker_before_closing_lane() -> None:
    source = BlockingSource()
    runtime = runtime_with(source, ScriptedCrossingProcessor())
    activate_session(runtime)
    runtime.application.configure_video_source(VideoSourceRequest.camera(0))
    runtime.application.start_counting_pipeline()
    assert source.read_entered.wait(1)

    snapshot = runtime.application.shutdown()

    assert runtime.counting_pipeline.snapshot().status is CountingPipelineStatus.STOPPED
    assert not runtime.counting_pipeline.snapshot().worker_alive
    assert snapshot.coordinator_closed
    assert not snapshot.counting_lane.occupied
    assert source.close_calls == 1
