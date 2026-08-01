from __future__ import annotations

from dataclasses import replace

from _phase9_helpers import LifecycleIdFactory, StepClock, registration
from _phase10_helpers import (
    ManualTime,
    StaticMemoryProbe,
    pipeline_snapshot,
    preview_snapshot,
    running_pipeline,
)

from hogflow.bootstrap import build_operator_runtime
from hogflow.camera import (
    CameraStatus,
    CountingPipelineStatus,
    PipelineFailureCategory,
    PreviewFailureCategory,
    PreviewHealthState,
)
from hogflow.domain import DockId
from hogflow.runtime import (
    ComponentHealthState,
    ProductionRuntimeConfiguration,
    RuntimeComponent,
    RuntimeHealthManager,
    RuntimeHealthState,
    RuntimeIssueCategory,
    RuntimeIssueDisposition,
    RuntimeWorkerState,
)


def manager(clock: ManualTime, **configuration) -> RuntimeHealthManager:
    return RuntimeHealthManager(
        ProductionRuntimeConfiguration(**configuration),
        clock=clock.wall,
        monotonic_clock=clock.monotonic,
        memory_probe=StaticMemoryProbe(clock),
    )


def runtime_snapshot():
    return build_operator_runtime().application.snapshot()


def test_initial_heartbeat_is_immutable_created_state_with_bounded_queues() -> None:
    clock = ManualTime()
    health = manager(clock)

    heartbeat = health.heartbeat(
        pipeline_snapshot(
            camera=replace(
                pipeline_snapshot().camera,
                source_id=None,
                display_name="Not configured",
                status=CameraStatus.NOT_CONFIGURED,
            )
        ),
        preview_snapshot(enabled=False, health_state=PreviewHealthState.DISABLED),
        runtime_snapshot(),
    )

    assert heartbeat.sequence == 1
    assert heartbeat.health_state is RuntimeHealthState.CREATED
    assert heartbeat.pipeline_queue_size == heartbeat.pipeline_queue_capacity == 0
    assert heartbeat.preview_queue_size == heartbeat.preview_queue_capacity == 0
    assert heartbeat.worker_state is RuntimeWorkerState.STOPPED
    assert tuple(item.component for item in heartbeat.components) == tuple(RuntimeComponent)
    assert heartbeat.memory.available


def test_running_heartbeat_aggregates_fps_latency_and_preview_slot() -> None:
    clock = ManualTime()
    health = manager(clock)
    pipeline = running_pipeline(clock)
    preview = preview_snapshot(frame_available=True, frames_published=1)

    heartbeat = health.heartbeat(pipeline, preview, runtime_snapshot())

    assert heartbeat.health_state is RuntimeHealthState.HEALTHY
    assert heartbeat.current_fps == 20.0
    assert heartbeat.last_processed_frame == 9
    assert heartbeat.preview_queue_size == 1
    assert heartbeat.preview_queue_capacity == 1
    assert heartbeat.diagnostics.average_fps == 20.0
    assert heartbeat.diagnostics.average_processing_latency_ms == 4.0
    assert heartbeat.diagnostics.maximum_processing_latency_ms == 8.0


def test_fps_aggregates_track_minimum_average_and_maximum() -> None:
    clock = ManualTime()
    health = manager(clock)
    runtime = runtime_snapshot()

    for fps in (10.0, 20.0, 30.0):
        heartbeat = health.heartbeat(
            running_pipeline(clock, effective_fps=fps),
            preview_snapshot(),
            runtime,
        )

    assert heartbeat.diagnostics.minimum_fps == 10.0
    assert heartbeat.diagnostics.average_fps == 20.0
    assert heartbeat.diagnostics.maximum_fps == 30.0


def test_heartbeat_observes_latest_successful_lane_count() -> None:
    clock = ManualTime()
    health = manager(clock)
    runtime = build_operator_runtime(
        clock=StepClock(),
        lifecycle_id_factory=LifecycleIdFactory(),
    )
    runtime.application.register_truck(registration())
    runtime.application.start_truck(DockId.DOCK_1)
    runtime.application.start_session(DockId.DOCK_1, "dock_1-session-1")
    snapshot = runtime.application.snapshot()
    dock = replace(
        snapshot.dock_snapshots[0],
        current_session_count=1,
        last_processed_frame=1,
    )
    snapshot = replace(
        snapshot,
        dock_snapshots=(dock, *snapshot.dock_snapshots[1:]),
        counting_lane=replace(
            snapshot.counting_lane,
            current_session_count=1,
            last_processed_frame=1,
        ),
    )

    heartbeat = health.heartbeat(
        running_pipeline(clock),
        preview_snapshot(),
        snapshot,
    )

    assert heartbeat.last_successful_count == 1
    assert heartbeat.last_successful_count_at == clock.wall()


def test_stalled_pipeline_and_stale_frame_are_recoverable() -> None:
    clock = ManualTime()
    health = manager(
        clock,
        stalled_pipeline_after_seconds=10,
        stale_frame_after_seconds=5,
    )
    pipeline = running_pipeline(clock)
    health.heartbeat(pipeline, preview_snapshot(), runtime_snapshot())
    clock.advance(11)

    heartbeat = health.heartbeat(pipeline, preview_snapshot(), runtime_snapshot())

    categories = {issue.category for issue in heartbeat.current_issues}
    assert RuntimeIssueCategory.PIPELINE_STALLED in categories
    assert RuntimeIssueCategory.STALE_FRAME in categories
    assert heartbeat.health_state is RuntimeHealthState.DEGRADED
    assert all(
        issue.disposition is RuntimeIssueDisposition.RECOVERABLE
        for issue in heartbeat.current_issues
    )


def test_dead_worker_is_fatal() -> None:
    clock = ManualTime()
    heartbeat = manager(clock).heartbeat(
        running_pipeline(clock, worker_alive=False),
        preview_snapshot(),
        runtime_snapshot(),
    )

    assert heartbeat.health_state is RuntimeHealthState.FAILED
    assert heartbeat.worker_state is RuntimeWorkerState.DEAD
    assert heartbeat.current_issues[0].category is RuntimeIssueCategory.WORKER_DEAD


def test_repeated_camera_and_detector_failures_cross_fatal_thresholds() -> None:
    clock = ManualTime()
    heartbeat = manager(
        clock,
        repeated_camera_failure_threshold=2,
        repeated_detector_failure_threshold=2,
    ).heartbeat(
        running_pipeline(
            clock,
            consecutive_camera_failures=2,
            consecutive_detector_failures=2,
            camera_failures=2,
            detector_failures=2,
        ),
        preview_snapshot(),
        runtime_snapshot(),
    )

    categories = {issue.category for issue in heartbeat.current_issues}
    assert RuntimeIssueCategory.REPEATED_CAMERA_FAILURES in categories
    assert RuntimeIssueCategory.REPEATED_DETECTOR_FAILURES in categories
    assert heartbeat.health_state is RuntimeHealthState.FAILED


def test_recovered_progress_clears_consecutive_failure_health() -> None:
    clock = ManualTime()
    health = manager(clock)
    failed = running_pipeline(
        clock,
        consecutive_camera_failures=1,
        camera_failures=1,
    )
    assert health.heartbeat(failed, preview_snapshot(), runtime_snapshot()).health_state is (
        RuntimeHealthState.DEGRADED
    )
    clock.advance(1)
    recovered = running_pipeline(
        clock,
        frames_processed=11,
        camera=replace(
            failed.camera,
            last_frame_index=10,
            frames_acquired=11,
            last_successful_frame_at=clock.wall(),
        ),
        consecutive_camera_failures=0,
        camera_failures=1,
    )

    assert health.heartbeat(recovered, preview_snapshot(), runtime_snapshot()).health_state is (
        RuntimeHealthState.HEALTHY
    )


def test_fatal_stage_categories_remain_fatal_and_source_failure_is_recoverable() -> None:
    clock = ManualTime()
    runtime = runtime_snapshot()
    for category, expected_disposition in (
        (PipelineFailureCategory.SOURCE_READ, RuntimeIssueDisposition.RECOVERABLE),
        (PipelineFailureCategory.DETECTOR, RuntimeIssueDisposition.RECOVERABLE),
        (PipelineFailureCategory.TRACKER, RuntimeIssueDisposition.FATAL),
        (PipelineFailureCategory.CROSSING, RuntimeIssueDisposition.FATAL),
    ):
        failed = pipeline_snapshot(
            status=CountingPipelineStatus.FAILED,
            camera=replace(
                pipeline_snapshot().camera,
                status=CameraStatus.FAILED,
                failure_category=category,
                failure_message="Sanitized stage failure.",
            ),
            failure_category=category,
            failure_message="Sanitized stage failure.",
        )
        heartbeat = manager(clock).heartbeat(failed, preview_snapshot(), runtime)
        assert heartbeat.current_issues[-1].disposition is expected_disposition


def test_preview_failure_is_recoverable_and_does_not_fail_counter_or_lane() -> None:
    clock = ManualTime()
    preview = preview_snapshot(
        health_state=PreviewHealthState.FAILED,
        render_failures=1,
        failure_category=PreviewFailureCategory.RENDERING,
        failure_message="Live preview rendering stopped; counting continues.",
    )

    heartbeat = manager(clock).heartbeat(
        running_pipeline(clock),
        preview,
        runtime_snapshot(),
    )

    assert heartbeat.health_state is RuntimeHealthState.DEGRADED
    assert heartbeat.current_issues[-1].category is RuntimeIssueCategory.PREVIEW_FAILURE
    component = {item.component: item.state for item in heartbeat.components}
    assert component[RuntimeComponent.PREVIEW] is ComponentHealthState.FAILED
    assert component[RuntimeComponent.COUNTER] is ComponentHealthState.IDLE
    assert component[RuntimeComponent.LANE] is ComponentHealthState.IDLE


def test_warning_history_and_diagnostics_remain_bounded() -> None:
    clock = ManualTime()
    health = manager(clock, warning_capacity=3)
    failed = running_pipeline(clock, worker_alive=False)

    for _ in range(20):
        heartbeat = health.heartbeat(failed, preview_snapshot(), runtime_snapshot())
        clock.advance(1)

    assert heartbeat.diagnostics.warnings_emitted >= 20
    assert len(heartbeat.diagnostics.recent_warnings) == 3
    assert heartbeat.diagnostics.warning_capacity == 3
    assert max(item.occurrences for item in heartbeat.diagnostics.recent_warnings) == 20


def test_pipeline_counter_resets_are_folded_into_lifetime_diagnostics() -> None:
    clock = ManualTime()
    health = manager(clock)
    runtime = runtime_snapshot()
    first = running_pipeline(
        clock,
        camera_failures=2,
        detector_failures=1,
        frames_dropped=3,
        recovery_attempts=1,
        recovery_successes=1,
    )
    health.heartbeat(first, preview_snapshot(publication_failures=1), runtime)
    health.record_pipeline_restart()
    reset_run = running_pipeline(
        clock,
        camera_failures=1,
        detector_failures=2,
        frames_dropped=4,
        recovery_attempts=1,
        recovery_successes=1,
        processing_samples=2,
        average_processing_latency_ms=2,
        maximum_processing_latency_ms=3,
    )

    diagnostics = health.heartbeat(
        reset_run,
        preview_snapshot(publication_failures=1),
        runtime,
    ).diagnostics

    assert diagnostics.camera_failures == 3
    assert diagnostics.detector_failures == 3
    assert diagnostics.frames_dropped == 7
    assert diagnostics.camera_reconnect_count == 2
    assert diagnostics.preview_failures == 1
    assert diagnostics.processing_samples == 12
