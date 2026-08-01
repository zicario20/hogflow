from __future__ import annotations

from dataclasses import replace

from _phase10_helpers import ManualTime, StaticMemoryProbe, preview_snapshot, running_pipeline

from hogflow.bootstrap import build_operator_runtime
from hogflow.runtime import ProductionRuntimeConfiguration, RuntimeHealthManager


def build_manager(clock: ManualTime) -> RuntimeHealthManager:
    return RuntimeHealthManager(
        ProductionRuntimeConfiguration(warning_capacity=8),
        clock=clock.wall,
        monotonic_clock=clock.monotonic,
        memory_probe=StaticMemoryProbe(clock),
    )


def test_ten_thousand_heartbeat_endurance_keeps_only_bounded_aggregates() -> None:
    clock = ManualTime()
    manager = build_manager(clock)
    runtime = build_operator_runtime().application.snapshot()
    pipeline = running_pipeline(clock)
    preview = preview_snapshot(frame_available=True)

    for sequence in range(10_000):
        camera = replace(
            pipeline.camera,
            last_frame_index=sequence,
            frames_acquired=sequence + 2,
            last_successful_frame_at=clock.wall(),
        )
        pipeline = replace(
            pipeline,
            camera=camera,
            frames_processed=sequence + 2,
            last_processed_frame_index=sequence,
            processing_samples=sequence + 2,
        )
        heartbeat = manager.heartbeat(pipeline, preview, runtime)
        clock.advance(0.05)

    assert heartbeat.sequence == 10_000
    assert heartbeat.diagnostics.heartbeat_count == 10_000
    assert heartbeat.diagnostics.fps_samples == 10_000
    assert len(heartbeat.diagnostics.recent_warnings) <= 8
    assert heartbeat.pipeline_queue_capacity == 0
    assert heartbeat.preview_queue_capacity == 1


def test_runtime_health_is_deterministic_for_the_same_observation_sequence() -> None:
    runtime = build_operator_runtime().application.snapshot()
    outputs = []
    for _ in range(2):
        clock = ManualTime()
        manager = build_manager(clock)
        pipeline = running_pipeline(clock)
        series = []
        for sequence in range(20):
            pipeline = replace(
                pipeline,
                camera=replace(
                    pipeline.camera,
                    last_frame_index=sequence,
                    frames_acquired=sequence + 2,
                    last_successful_frame_at=clock.wall(),
                ),
                frames_processed=sequence + 2,
                last_processed_frame_index=sequence,
                processing_samples=sequence + 2,
            )
            heartbeat = manager.heartbeat(pipeline, preview_snapshot(), runtime)
            series.append(
                (
                    heartbeat.health_state,
                    heartbeat.worker_state,
                    heartbeat.diagnostics.average_fps,
                    heartbeat.diagnostics.average_processing_latency_ms,
                    heartbeat.diagnostics.warnings_emitted,
                )
            )
            clock.advance(1)
        outputs.append(tuple(series))

    assert outputs[0] == outputs[1]
