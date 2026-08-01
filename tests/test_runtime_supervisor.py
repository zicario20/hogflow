from __future__ import annotations

from dataclasses import replace

import pytest
from _phase9_helpers import LifecycleIdFactory, StepClock, registration
from _phase10_helpers import ManualTime, StaticMemoryProbe, pipeline_snapshot, preview_snapshot

from hogflow.bootstrap import build_operator_runtime
from hogflow.camera import CameraPipelineLifecycleError
from hogflow.domain import DockId
from hogflow.runtime import (
    ProductionRuntimeConfiguration,
    ProductionRuntimeLifecycleError,
    ProductionRuntimeSupervisor,
    RuntimeHealthManager,
    RuntimeRestartLimitError,
    UnsafeRuntimeRestartError,
)


def same_runtime_state(left, right) -> bool:
    return replace(left, generated_at=right.generated_at) == right


class FakePipeline:
    def __init__(self) -> None:
        self.current = pipeline_snapshot()
        self.preview = preview_snapshot()
        self.restart_calls = 0
        self.preview_restart_calls = 0
        self.restart_error: Exception | None = None

    def snapshot(self):
        return self.current

    def preview_snapshot(self):
        return self.preview

    def restart(self):
        self.restart_calls += 1
        if self.restart_error is not None:
            raise self.restart_error
        return self.current

    def restart_preview(self):
        self.preview_restart_calls += 1
        self.preview = preview_snapshot()
        return self.preview


def supervisor(maximum_restarts: int = 3):
    clock = ManualTime()
    runtime = build_operator_runtime(
        clock=StepClock(),
        lifecycle_id_factory=LifecycleIdFactory(),
    )
    pipeline = FakePipeline()
    health = RuntimeHealthManager(
        ProductionRuntimeConfiguration(maximum_manual_restarts=maximum_restarts),
        clock=clock.wall,
        monotonic_clock=clock.monotonic,
        memory_probe=StaticMemoryProbe(clock),
    )
    return ProductionRuntimeSupervisor(pipeline, runtime.runtime_access, health), pipeline, runtime


def activate_lane(runtime) -> None:
    runtime.application.register_truck(registration(DockId.DOCK_1))
    runtime.application.start_truck(DockId.DOCK_1)
    runtime.application.start_session(DockId.DOCK_1, "dock_1-session-1")


def test_composition_root_creates_one_runtime_supervisor() -> None:
    runtime = build_operator_runtime()

    heartbeat = runtime.runtime_supervisor.heartbeat()

    assert heartbeat.sequence == 1
    assert runtime.runtime_supervisor.pipeline_snapshot() == runtime.counting_pipeline.snapshot()


def test_camera_restart_reuses_one_pipeline_and_records_bounded_diagnostics() -> None:
    subject, pipeline, runtime = supervisor()
    before = runtime.application.snapshot()

    heartbeat = subject.restart_camera()

    assert pipeline.restart_calls == 1
    assert same_runtime_state(runtime.application.snapshot(), before)
    assert heartbeat.diagnostics.camera_restart_count == 1
    assert heartbeat.diagnostics.camera_reconnect_count == 0
    assert heartbeat.diagnostics.worker_restart_count == 1


def test_pipeline_restart_records_pipeline_and_worker_restart() -> None:
    subject, pipeline, _runtime = supervisor()

    heartbeat = subject.restart_pipeline()

    assert pipeline.restart_calls == 1
    assert heartbeat.diagnostics.pipeline_restart_count == 1
    assert heartbeat.diagnostics.worker_restart_count == 1


def test_identity_resetting_restarts_are_blocked_while_lane_is_occupied() -> None:
    subject, pipeline, runtime = supervisor()
    activate_lane(runtime)
    before = runtime.application.snapshot()

    with pytest.raises(UnsafeRuntimeRestartError, match="blocked"):
        subject.restart_camera()
    with pytest.raises(UnsafeRuntimeRestartError, match="blocked"):
        subject.restart_pipeline()

    assert pipeline.restart_calls == 0
    assert same_runtime_state(runtime.application.snapshot(), before)


def test_preview_restart_is_allowed_during_counting_and_preserves_lane_count() -> None:
    subject, pipeline, runtime = supervisor()
    activate_lane(runtime)
    before = runtime.application.snapshot()

    preview = subject.restart_preview()
    heartbeat = subject.heartbeat()

    assert pipeline.preview_restart_calls == 1
    assert preview == preview_snapshot()
    assert same_runtime_state(runtime.application.snapshot(), before)
    assert heartbeat.diagnostics.preview_restart_count == 1


def test_restart_budget_is_bounded() -> None:
    subject, pipeline, _runtime = supervisor(maximum_restarts=1)
    subject.restart_pipeline()

    with pytest.raises(RuntimeRestartLimitError, match="budget"):
        subject.restart_pipeline()

    assert pipeline.restart_calls == 1


def test_failed_restart_does_not_consume_restart_telemetry() -> None:
    subject, pipeline, _runtime = supervisor()
    pipeline.restart_error = CameraPipelineLifecycleError("synthetic restart failure")

    with pytest.raises(CameraPipelineLifecycleError):
        subject.restart_pipeline()

    pipeline.restart_error = None
    heartbeat = subject.heartbeat()
    assert heartbeat.diagnostics.pipeline_restart_count == 0
    assert heartbeat.diagnostics.worker_restart_count == 0


def test_supervisor_close_is_idempotent_and_rejects_new_restarts() -> None:
    subject, pipeline, _runtime = supervisor()

    subject.close()
    subject.close()

    with pytest.raises(ProductionRuntimeLifecycleError, match="closed"):
        subject.restart_preview()
    with pytest.raises(ProductionRuntimeLifecycleError, match="closed"):
        subject.restart_pipeline()
    assert pipeline.restart_calls == 0
