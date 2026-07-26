"""Stateless operator workflow over the public Phase 8 coordinator."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from hogflow.application.models import (
    RegisterTruckCommand,
    VideoSourceKind,
    VideoSourceRequest,
)
from hogflow.application.runtime_access import SerializedMultiDockRuntimeAccess
from hogflow.camera import (
    CameraPipelineLifecycleError,
    CameraSnapshot,
    CameraStatus,
    CountingPipelineController,
    CountingPipelineSnapshot,
    CountingPipelineStatus,
    PipelineFailureCategory,
    PreviewFailureCategory,
    PreviewFrame,
    PreviewHealthState,
    PreviewSnapshot,
)
from hogflow.domain import DockId
from hogflow.sessions import MultiDockRuntimeCoordinator, MultiDockRuntimeSnapshot

Clock = Callable[[], datetime]
CrossingLifecycleIdFactory = Callable[[DockId, str], str]


class OperatorApplicationService:
    """Translate operator intent into public coordinator calls.

    The service owns no business state and no snapshot cache. Phase 8 remains
    the only source of truth. The composition root supplies both the camera
    pipeline and the crossing-lifecycle identity factory.
    """

    def __init__(
        self,
        coordinator: MultiDockRuntimeCoordinator,
        *,
        crossing_lifecycle_id_factory: CrossingLifecycleIdFactory,
        clock: Clock | None = None,
        runtime_access: SerializedMultiDockRuntimeAccess | None = None,
        counting_pipeline: CountingPipelineController | None = None,
    ) -> None:
        if not isinstance(coordinator, MultiDockRuntimeCoordinator):
            raise TypeError("Operator application requires a multi-dock runtime coordinator.")
        if not callable(crossing_lifecycle_id_factory):
            raise TypeError("Crossing lifecycle ID factory must be callable.")
        if clock is not None and not callable(clock):
            raise TypeError("Operator application clock must be callable.")
        self._runtime = runtime_access or SerializedMultiDockRuntimeAccess(coordinator)
        self._counting_pipeline = counting_pipeline
        self._crossing_lifecycle_id_factory = crossing_lifecycle_id_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def snapshot(self) -> MultiDockRuntimeSnapshot:
        """Read fresh Phase 8 state without retaining a presentation mirror."""

        return self._runtime.snapshot()

    def register_truck(self, command: RegisterTruckCommand) -> MultiDockRuntimeSnapshot:
        """Register one complete planned operation through the coordinator."""

        if not isinstance(command, RegisterTruckCommand):
            raise TypeError("Register truck requires an immutable operator command.")
        self._runtime.register_operation(command.dock_id, command.to_operation())
        return self.snapshot()

    def start_truck(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Start one planned truck using the application clock."""

        self._runtime.start_operation(dock_id, self._clock())
        return self.snapshot()

    def start_session(self, dock_id: DockId, session_id: str) -> MultiDockRuntimeSnapshot:
        """Bind the shared lane using an externally supplied lifecycle identity."""

        crossing_lifecycle_id = self._crossing_lifecycle_id_factory(dock_id, session_id)
        self._runtime.start_session(
            dock_id,
            session_id,
            crossing_lifecycle_id,
            self._clock(),
        )
        return self.snapshot()

    def complete_session(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Finalize the active session through Phase 8.2/8.4."""

        self._runtime.complete_session(dock_id, self._clock())
        return self.snapshot()

    def cancel_session(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Cancel the active session through Phase 8.2/8.4."""

        self._runtime.cancel_session(dock_id, self._clock())
        return self.snapshot()

    def complete_truck(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Complete one eligible operation through Phase 8.1."""

        self._runtime.complete_operation(dock_id, self._clock())
        return self.snapshot()

    def cancel_truck(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Cancel one operation through Phase 8.1."""

        self._runtime.cancel_operation(dock_id, self._clock())
        return self.snapshot()

    def shutdown(self) -> MultiDockRuntimeSnapshot:
        """Close the shared counter and cancel only an active lane binding."""

        if self._counting_pipeline is not None:
            self._counting_pipeline.close()
        self._runtime.close()
        return self.snapshot()

    def configure_video_source(
        self,
        request: VideoSourceRequest,
    ) -> CountingPipelineSnapshot:
        """Configure one source through the camera orchestration boundary."""

        if not isinstance(request, VideoSourceRequest):
            raise TypeError("Configure video source requires an immutable request.")
        self._require_runtime_open()
        controller = self._require_counting_pipeline()
        if request.kind is VideoSourceKind.CAMERA:
            assert request.camera_index is not None
            return controller.configure_camera(request.camera_index)
        assert request.local_file is not None
        return controller.configure_file(request.local_file)

    def start_counting_pipeline(self) -> CountingPipelineSnapshot:
        """Start the one shared camera pipeline."""

        self._require_runtime_open()
        return self._require_counting_pipeline().start()

    def stop_counting_pipeline(self) -> CountingPipelineSnapshot:
        """Stop the one shared camera pipeline."""

        return self._require_counting_pipeline().stop()

    def camera_snapshot(self) -> CameraSnapshot:
        """Return a camera snapshot without exposing infrastructure."""

        return self.pipeline_snapshot().camera

    def pipeline_snapshot(self) -> CountingPipelineSnapshot:
        """Return an immutable pipeline snapshot or explicit no-camera state."""

        if self._counting_pipeline is not None:
            return self._counting_pipeline.snapshot()
        return CountingPipelineSnapshot(
            status=CountingPipelineStatus.STOPPED,
            camera=CameraSnapshot(
                source_id=None,
                source_type=None,
                display_name="Not configured",
                status=CameraStatus.NOT_CONFIGURED,
                last_frame_index=None,
                frames_acquired=0,
                last_successful_frame_at=None,
                source_exhausted=False,
                failure_category=PipelineFailureCategory.NONE,
                failure_message=None,
            ),
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

    def latest_preview_frame(self) -> PreviewFrame | None:
        """Consume only the newest optional frame through the application API."""

        if self._counting_pipeline is None:
            return None
        return self._counting_pipeline.latest_preview_frame()

    def preview_snapshot(self) -> PreviewSnapshot:
        """Return visual availability without exposing the channel itself."""

        if self._counting_pipeline is not None:
            return self._counting_pipeline.preview_snapshot()
        return PreviewSnapshot(
            enabled=False,
            health_state=PreviewHealthState.DISABLED,
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

    def record_preview_render_failure(self) -> PreviewSnapshot:
        """Record renderer failure without changing camera/counting lifecycle."""

        if self._counting_pipeline is None:
            return self.preview_snapshot()
        return self._counting_pipeline.record_preview_render_failure()

    def _require_counting_pipeline(self) -> CountingPipelineController:
        if self._counting_pipeline is None:
            raise CameraPipelineLifecycleError(
                "Camera pipeline is unavailable in this no-camera composition."
            )
        return self._counting_pipeline

    def _require_runtime_open(self) -> None:
        if self._runtime.snapshot().coordinator_closed:
            raise CameraPipelineLifecycleError(
                "Camera pipeline commands are unavailable after application shutdown."
            )


__all__ = [
    "Clock",
    "CrossingLifecycleIdFactory",
    "OperatorApplicationService",
]
