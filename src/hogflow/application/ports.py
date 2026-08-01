"""Public application protocol consumed by the operator presentation."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hogflow.application.models import RegisterTruckCommand, VideoSourceRequest
from hogflow.camera import (
    CameraSnapshot,
    CountingPipelineSnapshot,
    PreviewFrame,
    PreviewSnapshot,
)
from hogflow.domain import DockId
from hogflow.sessions import MultiDockRuntimeSnapshot


@runtime_checkable
class OperatorApplication(Protocol):
    """Operator commands over the public Phase 8 runtime coordinator."""

    def snapshot(self) -> MultiDockRuntimeSnapshot:
        """Return the current immutable runtime snapshot."""

    def register_truck(self, command: RegisterTruckCommand) -> MultiDockRuntimeSnapshot:
        """Register one planned operation and return a fresh snapshot."""

    def start_truck(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Start one planned truck operation."""

    def start_session(self, dock_id: DockId, session_id: str) -> MultiDockRuntimeSnapshot:
        """Start one unloading session using a fresh crossing lifecycle."""

    def complete_session(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Finalize the lane count into the active unloading session."""

    def cancel_session(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Cancel the active unloading session and discard its live count."""

    def complete_truck(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Complete one eligible truck operation."""

    def cancel_truck(self, dock_id: DockId) -> MultiDockRuntimeSnapshot:
        """Cancel one truck operation."""

    def shutdown(self) -> MultiDockRuntimeSnapshot:
        """Close the shared runtime safely and return its terminal snapshot."""

    def configure_video_source(
        self,
        request: VideoSourceRequest,
    ) -> CountingPipelineSnapshot:
        """Configure one local source without opening it."""

    def start_counting_pipeline(self) -> CountingPipelineSnapshot:
        """Start the one shared camera worker."""

    def stop_counting_pipeline(self) -> CountingPipelineSnapshot:
        """Stop the one shared camera worker."""

    def restart_video(self) -> CountingPipelineSnapshot:
        """Replay the configured local video after normal end of file."""

    def camera_snapshot(self) -> CameraSnapshot:
        """Return the current immutable camera state."""

    def pipeline_snapshot(self) -> CountingPipelineSnapshot:
        """Return the current immutable pipeline state."""

    def latest_preview_frame(self) -> PreviewFrame | None:
        """Consume the newest optional visual frame without infrastructure access."""

    def preview_snapshot(self) -> PreviewSnapshot:
        """Return bounded preview availability and telemetry."""

    def record_preview_render_failure(self) -> PreviewSnapshot:
        """Isolate one presentation renderer failure from counting."""


__all__ = ["OperatorApplication"]
