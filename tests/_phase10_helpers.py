from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from hogflow.camera import (
    CameraSnapshot,
    CameraStatus,
    CountingPipelineSnapshot,
    CountingPipelineStatus,
    PipelineFailureCategory,
    PreviewFailureCategory,
    PreviewHealthState,
    PreviewSnapshot,
)
from hogflow.runtime import ProcessMemorySnapshot


class ManualTime:
    def __init__(self) -> None:
        self.value = 0.0
        self.started = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def advance(self, seconds: float) -> None:
        self.value += seconds

    def monotonic(self) -> float:
        return self.value

    def wall(self) -> datetime:
        return self.started + timedelta(seconds=self.value)


class StaticMemoryProbe:
    def __init__(self, clock: ManualTime, resident: int = 10_000) -> None:
        self.clock = clock
        self.resident = resident
        self.calls = 0

    def snapshot(self) -> ProcessMemorySnapshot:
        self.calls += 1
        return ProcessMemorySnapshot(
            self.clock.wall(),
            True,
            self.resident,
            self.resident + 1_000,
        )


def pipeline_snapshot(**changes) -> CountingPipelineSnapshot:
    camera = changes.pop(
        "camera",
        CameraSnapshot(
            source_id="shared_operator_lane",
            source_type=None,
            display_name="Synthetic runtime source",
            status=CameraStatus.CLOSED,
            last_frame_index=None,
            frames_acquired=0,
            last_successful_frame_at=None,
            source_exhausted=False,
            failure_category=PipelineFailureCategory.NONE,
            failure_message=None,
        ),
    )
    snapshot = CountingPipelineSnapshot(
        status=CountingPipelineStatus.STOPPED,
        camera=camera,
        frames_processed=0,
        temporary_processing_failures=0,
        stale_results_rejected=0,
        active_crossing_lifecycle_id=None,
        worker_alive=False,
        failure_category=PipelineFailureCategory.NONE,
        failure_message=None,
        started_at=None,
        stopped_at=None,
    )
    return replace(snapshot, **changes)


def running_pipeline(clock: ManualTime, **changes) -> CountingPipelineSnapshot:
    camera = CameraSnapshot(
        source_id="shared_operator_lane",
        source_type=None,
        display_name="Synthetic runtime source",
        status=CameraStatus.RUNNING,
        last_frame_index=9,
        frames_acquired=10,
        last_successful_frame_at=clock.wall(),
        source_exhausted=False,
        failure_category=PipelineFailureCategory.NONE,
        failure_message=None,
    )
    values = {
        "status": CountingPipelineStatus.RUNNING,
        "camera": camera,
        "frames_processed": 10,
        "last_processed_frame_index": 9,
        "worker_alive": True,
        "started_at": clock.wall(),
        "effective_fps": 20.0,
        "processing_samples": 10,
        "average_processing_latency_ms": 4.0,
        "maximum_processing_latency_ms": 8.0,
    }
    values.update(changes)
    return pipeline_snapshot(**values)


def preview_snapshot(**changes) -> PreviewSnapshot:
    snapshot = PreviewSnapshot(
        enabled=True,
        health_state=PreviewHealthState.WAITING,
        frame_available=False,
        frames_published=0,
        frames_replaced=0,
        frames_consumed=0,
        publication_failures=0,
        render_failures=0,
        effective_preview_fps=0.0,
        last_frame_sequence=None,
        failure_category=PreviewFailureCategory.NONE,
        failure_message=None,
    )
    return replace(snapshot, **changes)


__all__ = [
    "ManualTime",
    "StaticMemoryProbe",
    "pipeline_snapshot",
    "preview_snapshot",
    "running_pipeline",
]
