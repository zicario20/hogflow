"""Synchronous bounded health aggregation for the production runtime."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import RLock
from time import monotonic
from typing import Callable

from hogflow.camera import (
    CameraStatus,
    CountingPipelineSnapshot,
    CountingPipelineStatus,
    PipelineFailureCategory,
    PreviewHealthState,
    PreviewSnapshot,
)
from hogflow.runtime.memory import StandardProcessMemoryProbe
from hogflow.runtime.models import (
    ComponentHealth,
    ComponentHealthState,
    ProductionRuntimeConfiguration,
    RuntimeComponent,
    RuntimeDiagnosticsSnapshot,
    RuntimeHealthState,
    RuntimeHeartbeat,
    RuntimeIssue,
    RuntimeIssueCategory,
    RuntimeIssueDisposition,
    RuntimeWorkerState,
)
from hogflow.runtime.ports import ProcessMemoryProbe
from hogflow.sessions import MultiDockRuntimeSnapshot

Clock = Callable[[], datetime]


class RuntimeHealthManager:
    """Create periodic immutable heartbeats without storing heartbeat history.

    The caller supplies the cadence. This class creates no thread or polling
    loop and stores only aggregate counters, one prior observation, and a
    fixed-capacity warning deque.
    """

    def __init__(
        self,
        configuration: ProductionRuntimeConfiguration = ProductionRuntimeConfiguration(),
        *,
        clock: Clock | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
        memory_probe: ProcessMemoryProbe | None = None,
    ) -> None:
        if not isinstance(configuration, ProductionRuntimeConfiguration):
            raise TypeError("Runtime health manager requires production configuration.")
        if not callable(monotonic_clock):
            raise TypeError("Runtime health manager monotonic clock must be callable.")
        self._configuration = configuration
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic_clock
        self._memory_probe = memory_probe or StandardProcessMemoryProbe(clock=self._clock)
        self._lock = RLock()
        self._started_at = float(self._monotonic())
        self._last_progress_at = self._started_at
        self._heartbeat_count = 0
        self._previous_pipeline: CountingPipelineSnapshot | None = None
        self._previous_preview: PreviewSnapshot | None = None
        self._previous_lane_lifecycle: str | None = None
        self._previous_lane_count = 0
        self._previous_finalized_count = 0
        self._last_successful_count: int | None = None
        self._last_successful_count_at: datetime | None = None
        self._fps_samples = 0
        self._fps_total = 0.0
        self._minimum_fps = 0.0
        self._maximum_fps = 0.0
        self._processing_samples = 0
        self._processing_latency_total = 0.0
        self._maximum_processing_latency = 0.0
        self._camera_reconnect_count = 0
        self._camera_restart_count = 0
        self._pipeline_restart_count = 0
        self._worker_restart_count = 0
        self._preview_restart_count = 0
        self._frames_dropped = 0
        self._camera_failures = 0
        self._detector_failures = 0
        self._tracker_failures = 0
        self._crossing_failures = 0
        self._preview_failures = 0
        self._stale_evidence_rejected = 0
        self._warnings_emitted = 0
        self._warning_occurrences = {category: 0 for category in RuntimeIssueCategory}
        self._recent_warnings: deque[RuntimeIssue] = deque(maxlen=configuration.warning_capacity)
        self._closed = False

    @property
    def configuration(self) -> ProductionRuntimeConfiguration:
        return self._configuration

    def heartbeat(
        self,
        pipeline: CountingPipelineSnapshot,
        preview: PreviewSnapshot,
        runtime: MultiDockRuntimeSnapshot,
    ) -> RuntimeHeartbeat:
        """Observe current public snapshots and return one immutable heartbeat."""

        if not isinstance(pipeline, CountingPipelineSnapshot):
            raise TypeError("Runtime heartbeat requires a pipeline snapshot.")
        if not isinstance(preview, PreviewSnapshot):
            raise TypeError("Runtime heartbeat requires a preview snapshot.")
        if not isinstance(runtime, MultiDockRuntimeSnapshot):
            raise TypeError("Runtime heartbeat requires a shared-lane snapshot.")
        with self._lock:
            now = self._clock()
            now_monotonic = float(self._monotonic())
            self._heartbeat_count += 1
            self._observe_diagnostics(pipeline, preview)
            self._observe_count(runtime, now)
            if (
                self._previous_pipeline is None
                or pipeline.frames_processed != self._previous_pipeline.frames_processed
            ):
                self._last_progress_at = now_monotonic
            issues = self._current_issues(pipeline, preview, runtime, now, now_monotonic)
            components = self._component_health(pipeline, preview, runtime)
            health = self._overall_health(pipeline, issues)
            worker_state = _worker_state(pipeline)
            self._previous_pipeline = pipeline
            self._previous_preview = preview
            diagnostics = self._diagnostics()
            return RuntimeHeartbeat(
                sequence=self._heartbeat_count,
                generated_at=now,
                uptime_seconds=max(0.0, now_monotonic - self._started_at),
                health_state=health,
                components=components,
                current_issues=issues,
                last_processed_frame=pipeline.last_processed_frame_index,
                last_successful_count=self._last_successful_count,
                last_successful_count_at=self._last_successful_count_at,
                current_fps=pipeline.effective_fps,
                memory=self._memory_probe.snapshot(),
                pipeline_queue_size=0,
                pipeline_queue_capacity=0,
                preview_queue_size=int(preview.frame_available),
                preview_queue_capacity=int(preview.enabled),
                worker_state=worker_state,
                diagnostics=diagnostics,
                configuration_fingerprint=self._configuration.fingerprint,
            )

    def record_camera_restart(self) -> None:
        with self._lock:
            self._camera_restart_count += 1
            self._worker_restart_count += 1
            self._previous_pipeline = None

    def record_pipeline_restart(self) -> None:
        with self._lock:
            self._pipeline_restart_count += 1
            self._worker_restart_count += 1
            self._previous_pipeline = None

    def record_preview_restart(self) -> None:
        with self._lock:
            self._preview_restart_count += 1
            self._previous_preview = None

    def stop(self) -> None:
        """Mark supervision stopped; no external resource is owned here."""

        with self._lock:
            self._closed = True

    def _observe_diagnostics(
        self,
        pipeline: CountingPipelineSnapshot,
        preview: PreviewSnapshot,
    ) -> None:
        previous = self._previous_pipeline
        previous_preview = self._previous_preview
        for name in (
            "recovery_successes",
            "frames_dropped",
            "camera_failures",
            "detector_failures",
            "tracker_failures",
            "crossing_failures",
            "stale_results_rejected",
        ):
            current_value = getattr(pipeline, name)
            previous_value = 0 if previous is None else getattr(previous, name)
            delta = _counter_delta(current_value, previous_value)
            target = {
                "recovery_successes": "_camera_reconnect_count",
                "frames_dropped": "_frames_dropped",
                "camera_failures": "_camera_failures",
                "detector_failures": "_detector_failures",
                "tracker_failures": "_tracker_failures",
                "crossing_failures": "_crossing_failures",
                "stale_results_rejected": "_stale_evidence_rejected",
            }[name]
            setattr(self, target, getattr(self, target) + delta)
        preview_total = preview.publication_failures + preview.render_failures
        previous_preview_total = (
            0
            if previous_preview is None
            else previous_preview.publication_failures + previous_preview.render_failures
        )
        self._preview_failures += _counter_delta(preview_total, previous_preview_total)

        if pipeline.effective_fps > 0:
            self._fps_samples += 1
            self._fps_total += pipeline.effective_fps
            if self._fps_samples == 1:
                self._minimum_fps = pipeline.effective_fps
            else:
                self._minimum_fps = min(self._minimum_fps, pipeline.effective_fps)
            self._maximum_fps = max(self._maximum_fps, pipeline.effective_fps)

        previous_samples = 0 if previous is None else previous.processing_samples
        sample_delta = _counter_delta(pipeline.processing_samples, previous_samples)
        if sample_delta:
            current_total = pipeline.average_processing_latency_ms * pipeline.processing_samples
            previous_total = (
                0.0
                if previous is None or pipeline.processing_samples < previous.processing_samples
                else previous.average_processing_latency_ms * previous.processing_samples
            )
            latency_delta = max(0.0, current_total - previous_total)
            self._processing_samples += sample_delta
            self._processing_latency_total += latency_delta
            self._maximum_processing_latency = max(
                self._maximum_processing_latency,
                pipeline.maximum_processing_latency_ms,
            )

    def _observe_count(self, runtime: MultiDockRuntimeSnapshot, now: datetime) -> None:
        lane = runtime.counting_lane
        lifecycle = lane.counting_lifecycle_id
        if lifecycle != self._previous_lane_lifecycle:
            self._previous_lane_lifecycle = lifecycle
            self._previous_lane_count = 0
        if lane.current_session_count > self._previous_lane_count:
            self._last_successful_count = lane.current_session_count
            self._last_successful_count_at = now
        elif runtime.aggregate_completed_pig_count > self._previous_finalized_count:
            self._last_successful_count = runtime.aggregate_completed_pig_count
            self._last_successful_count_at = now
        self._previous_lane_count = lane.current_session_count
        self._previous_finalized_count = runtime.aggregate_completed_pig_count

    def _current_issues(
        self,
        pipeline: CountingPipelineSnapshot,
        preview: PreviewSnapshot,
        runtime: MultiDockRuntimeSnapshot,
        now: datetime,
        now_monotonic: float,
    ) -> tuple[RuntimeIssue, ...]:
        issues: list[RuntimeIssue] = []
        if (
            pipeline.status
            in (
                CountingPipelineStatus.STARTING,
                CountingPipelineStatus.RUNNING,
            )
            and not pipeline.worker_alive
        ):
            issues.append(
                self._issue(
                    RuntimeIssueCategory.WORKER_DEAD,
                    RuntimeComponent.WORKER,
                    RuntimeIssueDisposition.FATAL,
                    "The shared counting worker is not alive while marked active.",
                    now,
                )
            )
        if (
            pipeline.status is CountingPipelineStatus.RUNNING
            and now_monotonic - self._last_progress_at
            >= self._configuration.stalled_pipeline_after_seconds
        ):
            issues.append(
                self._issue(
                    RuntimeIssueCategory.PIPELINE_STALLED,
                    RuntimeComponent.PIPELINE,
                    RuntimeIssueDisposition.RECOVERABLE,
                    "The shared counting pipeline has made no processing progress.",
                    now,
                )
            )
        if pipeline.status is CountingPipelineStatus.RUNNING:
            frame_time = pipeline.camera.last_successful_frame_at or pipeline.started_at
            if frame_time is not None and max(0.0, (now - frame_time).total_seconds()) >= (
                self._configuration.stale_frame_after_seconds
            ):
                issues.append(
                    self._issue(
                        RuntimeIssueCategory.STALE_FRAME,
                        RuntimeComponent.CAMERA,
                        RuntimeIssueDisposition.RECOVERABLE,
                        "The shared source has not produced a recent successful frame.",
                        now,
                    )
                )
        if pipeline.consecutive_camera_failures:
            repeated = pipeline.consecutive_camera_failures >= (
                self._configuration.repeated_camera_failure_threshold
            )
            issues.append(
                self._issue(
                    (
                        RuntimeIssueCategory.REPEATED_CAMERA_FAILURES
                        if repeated
                        else RuntimeIssueCategory.CAMERA_FAILURE
                    ),
                    RuntimeComponent.CAMERA,
                    (
                        RuntimeIssueDisposition.FATAL
                        if repeated
                        else RuntimeIssueDisposition.RECOVERABLE
                    ),
                    (
                        "The shared source exceeded its consecutive failure threshold."
                        if repeated
                        else "The shared source reported a recoverable frame failure."
                    ),
                    now,
                )
            )
        if pipeline.consecutive_detector_failures:
            repeated = pipeline.consecutive_detector_failures >= (
                self._configuration.repeated_detector_failure_threshold
            )
            issues.append(
                self._issue(
                    (
                        RuntimeIssueCategory.REPEATED_DETECTOR_FAILURES
                        if repeated
                        else RuntimeIssueCategory.DETECTOR_FAILURE
                    ),
                    RuntimeComponent.PIPELINE,
                    (
                        RuntimeIssueDisposition.FATAL
                        if repeated
                        else RuntimeIssueDisposition.RECOVERABLE
                    ),
                    (
                        "Detector failures exceeded the configured consecutive threshold."
                        if repeated
                        else "Detector processing reported a recoverable failure."
                    ),
                    now,
                )
            )
        if pipeline.status is CountingPipelineStatus.FAILED:
            issue = _pipeline_failure_issue(pipeline.failure_category)
            if issue is not None and not any(existing.category is issue[0] for existing in issues):
                issues.append(self._issue(*issue, now))
        if preview.health_state is PreviewHealthState.FAILED:
            issues.append(
                self._issue(
                    RuntimeIssueCategory.PREVIEW_FAILURE,
                    RuntimeComponent.PREVIEW,
                    RuntimeIssueDisposition.RECOVERABLE,
                    "Optional preview failed; counting remains independent.",
                    now,
                )
            )
        if runtime.coordinator_closed and pipeline.worker_alive:
            issues.append(
                self._issue(
                    RuntimeIssueCategory.LANE_FAILURE,
                    RuntimeComponent.LANE,
                    RuntimeIssueDisposition.FATAL,
                    "The counting lane is closed while the worker remains active.",
                    now,
                )
            )
        return tuple(issues)

    def _issue(
        self,
        category: RuntimeIssueCategory,
        component: RuntimeComponent,
        disposition: RuntimeIssueDisposition,
        message: str,
        observed_at: datetime,
    ) -> RuntimeIssue:
        self._warning_occurrences[category] += 1
        issue = RuntimeIssue(
            category,
            component,
            disposition,
            message,
            observed_at,
            self._warning_occurrences[category],
        )
        self._warnings_emitted += 1
        self._recent_warnings.append(issue)
        return issue

    def _component_health(
        self,
        pipeline: CountingPipelineSnapshot,
        preview: PreviewSnapshot,
        runtime: MultiDockRuntimeSnapshot,
    ) -> tuple[ComponentHealth, ...]:
        lane_state = (
            ComponentHealthState.STOPPED
            if runtime.counting_lane.closed
            else ComponentHealthState.HEALTHY
            if runtime.counting_lane.occupied
            else ComponentHealthState.IDLE
        )
        return (
            ComponentHealth(RuntimeComponent.WORKER, _worker_health(pipeline)),
            ComponentHealth(RuntimeComponent.CAMERA, _camera_health(pipeline.camera.status)),
            ComponentHealth(RuntimeComponent.PIPELINE, _pipeline_health(pipeline.status)),
            ComponentHealth(RuntimeComponent.PREVIEW, _preview_health(preview.health_state)),
            ComponentHealth(RuntimeComponent.COUNTER, lane_state),
            ComponentHealth(RuntimeComponent.LANE, lane_state),
        )

    def _overall_health(
        self,
        pipeline: CountingPipelineSnapshot,
        issues: tuple[RuntimeIssue, ...],
    ) -> RuntimeHealthState:
        if self._closed:
            return RuntimeHealthState.STOPPED
        if any(item.disposition is RuntimeIssueDisposition.FATAL for item in issues):
            return RuntimeHealthState.FAILED
        if issues:
            return RuntimeHealthState.DEGRADED
        if (
            pipeline.camera.status is CameraStatus.NOT_CONFIGURED
            and pipeline.status is CountingPipelineStatus.STOPPED
        ):
            return RuntimeHealthState.CREATED
        return RuntimeHealthState.HEALTHY

    def _diagnostics(self) -> RuntimeDiagnosticsSnapshot:
        return RuntimeDiagnosticsSnapshot(
            heartbeat_count=self._heartbeat_count,
            fps_samples=self._fps_samples,
            average_fps=(self._fps_total / self._fps_samples if self._fps_samples else 0.0),
            minimum_fps=self._minimum_fps,
            maximum_fps=self._maximum_fps,
            processing_samples=self._processing_samples,
            average_processing_latency_ms=(
                self._processing_latency_total / self._processing_samples
                if self._processing_samples
                else 0.0
            ),
            maximum_processing_latency_ms=self._maximum_processing_latency,
            camera_reconnect_count=self._camera_reconnect_count,
            camera_restart_count=self._camera_restart_count,
            pipeline_restart_count=self._pipeline_restart_count,
            worker_restart_count=self._worker_restart_count,
            preview_restart_count=self._preview_restart_count,
            frames_dropped=self._frames_dropped,
            camera_failures=self._camera_failures,
            detector_failures=self._detector_failures,
            tracker_failures=self._tracker_failures,
            crossing_failures=self._crossing_failures,
            preview_failures=self._preview_failures,
            stale_evidence_rejected=self._stale_evidence_rejected,
            warnings_emitted=self._warnings_emitted,
            recent_warnings=tuple(self._recent_warnings),
            warning_capacity=self._configuration.warning_capacity,
        )


def _counter_delta(current: int, previous: int) -> int:
    return current - previous if current >= previous else current


def _worker_state(snapshot: CountingPipelineSnapshot) -> RuntimeWorkerState:
    if snapshot.worker_alive:
        if snapshot.status is CountingPipelineStatus.STARTING:
            return RuntimeWorkerState.STARTING
        if snapshot.status is CountingPipelineStatus.STOPPING:
            return RuntimeWorkerState.STOPPING
        return RuntimeWorkerState.RUNNING
    if snapshot.status in (CountingPipelineStatus.STARTING, CountingPipelineStatus.RUNNING):
        return RuntimeWorkerState.DEAD
    if snapshot.status is CountingPipelineStatus.FAILED:
        return RuntimeWorkerState.FAILED
    return RuntimeWorkerState.STOPPED


def _worker_health(snapshot: CountingPipelineSnapshot) -> ComponentHealthState:
    state = _worker_state(snapshot)
    if state in (RuntimeWorkerState.DEAD, RuntimeWorkerState.FAILED):
        return ComponentHealthState.FAILED
    if state is RuntimeWorkerState.STOPPED:
        return ComponentHealthState.STOPPED
    return ComponentHealthState.HEALTHY


def _camera_health(state: CameraStatus) -> ComponentHealthState:
    if state is CameraStatus.RUNNING:
        return ComponentHealthState.HEALTHY
    if state in (CameraStatus.OPENING, CameraStatus.DISCONNECTED):
        return ComponentHealthState.DEGRADED
    if state is CameraStatus.FAILED:
        return ComponentHealthState.FAILED
    if state is CameraStatus.NOT_CONFIGURED:
        return ComponentHealthState.IDLE
    return ComponentHealthState.STOPPED


def _pipeline_health(state: CountingPipelineStatus) -> ComponentHealthState:
    if state is CountingPipelineStatus.RUNNING:
        return ComponentHealthState.HEALTHY
    if state in (CountingPipelineStatus.STARTING, CountingPipelineStatus.STOPPING):
        return ComponentHealthState.DEGRADED
    if state is CountingPipelineStatus.FAILED:
        return ComponentHealthState.FAILED
    return ComponentHealthState.STOPPED


def _preview_health(state: PreviewHealthState) -> ComponentHealthState:
    if state in (PreviewHealthState.AVAILABLE, PreviewHealthState.WAITING):
        return ComponentHealthState.HEALTHY
    if state is PreviewHealthState.DEGRADED:
        return ComponentHealthState.DEGRADED
    if state is PreviewHealthState.FAILED:
        return ComponentHealthState.FAILED
    if state is PreviewHealthState.DISABLED:
        return ComponentHealthState.IDLE
    return ComponentHealthState.STOPPED


def _pipeline_failure_issue(
    category: PipelineFailureCategory,
) -> tuple[RuntimeIssueCategory, RuntimeComponent, RuntimeIssueDisposition, str] | None:
    if category in (PipelineFailureCategory.SOURCE_OPEN, PipelineFailureCategory.SOURCE_READ):
        return (
            RuntimeIssueCategory.CAMERA_FAILURE,
            RuntimeComponent.CAMERA,
            RuntimeIssueDisposition.RECOVERABLE,
            "The shared source failed and requires a controlled restart.",
        )
    if category is PipelineFailureCategory.DETECTOR:
        return (
            RuntimeIssueCategory.DETECTOR_FAILURE,
            RuntimeComponent.PIPELINE,
            RuntimeIssueDisposition.RECOVERABLE,
            "Detector processing failed and requires a controlled pipeline restart.",
        )
    if category is PipelineFailureCategory.TRACKER:
        return (
            RuntimeIssueCategory.TRACKER_FAILURE,
            RuntimeComponent.PIPELINE,
            RuntimeIssueDisposition.FATAL,
            "Tracker state cannot be trusted after the pipeline failure.",
        )
    if category is PipelineFailureCategory.CROSSING:
        return (
            RuntimeIssueCategory.CROSSING_FAILURE,
            RuntimeComponent.PIPELINE,
            RuntimeIssueDisposition.FATAL,
            "Crossing state cannot be trusted after the pipeline failure.",
        )
    if category is PipelineFailureCategory.NONE:
        return None
    return (
        RuntimeIssueCategory.PIPELINE_FAILURE,
        RuntimeComponent.PIPELINE,
        RuntimeIssueDisposition.FATAL,
        "The shared counting pipeline requires explicit operator recovery.",
    )


__all__ = ["Clock", "RuntimeHealthManager"]
