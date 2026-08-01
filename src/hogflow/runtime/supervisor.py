"""Controlled synchronous supervision and restart operations."""

from __future__ import annotations

from threading import RLock

from hogflow.camera import CountingPipelineSnapshot, PreviewSnapshot
from hogflow.runtime.errors import (
    ProductionRuntimeLifecycleError,
    RuntimeRestartLimitError,
    UnsafeRuntimeRestartError,
)
from hogflow.runtime.health import RuntimeHealthManager
from hogflow.runtime.models import ProductionRuntimeConfiguration, RuntimeHeartbeat
from hogflow.runtime.ports import SupervisedCountingPipeline, SupervisedRuntimeAccess


class ProductionRuntimeSupervisor:
    """Observe and explicitly restart the existing shared runtime.

    The supervisor creates no thread. Camera and full-pipeline restart both
    recreate the existing one-worker/source composition. By default they are
    rejected while the shared lane is occupied because tracker reset can break
    temporary-identity continuity and therefore compromise active counting.
    Preview restart is always isolated from counting state.
    """

    def __init__(
        self,
        pipeline: SupervisedCountingPipeline,
        runtime: SupervisedRuntimeAccess,
        health_manager: RuntimeHealthManager,
    ) -> None:
        required_pipeline = (
            pipeline.snapshot,
            pipeline.preview_snapshot,
            pipeline.restart,
            pipeline.restart_preview,
        )
        if not all(callable(item) for item in required_pipeline):
            raise TypeError("Runtime supervisor requires the public pipeline operations.")
        if not callable(runtime.snapshot):
            raise TypeError("Runtime supervisor requires serialized runtime snapshots.")
        if not isinstance(health_manager, RuntimeHealthManager):
            raise TypeError("Runtime supervisor requires RuntimeHealthManager.")
        self._pipeline = pipeline
        self._runtime = runtime
        self._health_manager = health_manager
        self._lock = RLock()
        self._manual_restarts = 0
        self._closed = False

    @property
    def configuration(self) -> ProductionRuntimeConfiguration:
        """Return immutable production-runtime configuration."""

        return self._health_manager.configuration

    def heartbeat(self) -> RuntimeHeartbeat:
        """Generate one current immutable heartbeat on caller cadence."""

        with self._lock:
            pipeline = self._pipeline.snapshot()
            preview = self._pipeline.preview_snapshot()
            runtime = self._runtime.snapshot()
            return self._health_manager.heartbeat(pipeline, preview, runtime)

    def restart_camera(self) -> RuntimeHeartbeat:
        """Recreate the one source/worker after an explicit safe request."""

        with self._lock:
            self._require_restart_safe()
            self._pipeline.restart()
            self._manual_restarts += 1
            self._health_manager.record_camera_restart()
            return self.heartbeat()

    def restart_pipeline(self) -> RuntimeHeartbeat:
        """Recreate the one processor/source/worker after an explicit request."""

        with self._lock:
            self._require_restart_safe()
            self._pipeline.restart()
            self._manual_restarts += 1
            self._health_manager.record_pipeline_restart()
            return self.heartbeat()

    def restart_preview(self) -> PreviewSnapshot:
        """Reset optional visual delivery without stopping counting."""

        with self._lock:
            self._require_open()
            result = self._pipeline.restart_preview()
            self._health_manager.record_preview_restart()
            return result

    def pipeline_snapshot(self) -> CountingPipelineSnapshot:
        """Return current one-worker status without producing a heartbeat."""

        return self._pipeline.snapshot()

    def close(self) -> None:
        """Stop supervision only; application shutdown still owns resources."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._health_manager.stop()

    def _require_restart_safe(self) -> None:
        self._require_open()
        if self._manual_restarts >= self.configuration.maximum_manual_restarts:
            raise RuntimeRestartLimitError(
                "Production runtime exhausted its bounded manual restart budget."
            )
        snapshot = self._runtime.snapshot()
        if self.configuration.require_idle_lane_for_restart and snapshot.counting_lane.occupied:
            raise UnsafeRuntimeRestartError(
                "Camera or pipeline restart is blocked while one counting session owns the lane."
            )

    def _require_open(self) -> None:
        if self._closed:
            raise ProductionRuntimeLifecycleError("Production runtime supervisor is closed.")


__all__ = ["ProductionRuntimeSupervisor"]
