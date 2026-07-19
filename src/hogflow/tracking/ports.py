"""Small framework-neutral contracts for live tracking and preview."""

from __future__ import annotations

from typing import Protocol

from hogflow.detection.inference import FrameDetections, LiveDetectionStats, PreviewAction
from hogflow.streaming.models import FramePacket
from hogflow.tracking.models import (
    LiveTrackingStats,
    TrackerMetadata,
    TrackingRequest,
    TrackingResult,
)


class LiveTracker(Protocol):
    """Own temporary identity state for one explicit stream lifecycle.

    Implementations accept immutable HogFlow detection data and return only
    immutable HogFlow tracking results. They make no thread-safety guarantee,
    expose no framework objects, and perform no detection, counting, crossing,
    session, persistence, rendering, or permanent identity work.
    """

    @property
    def metadata(self) -> TrackerMetadata:
        """Return sanitized tracker provenance after successful startup."""

        ...

    @property
    def is_started(self) -> bool:
        """Return whether tracker state is available for updates."""

        ...

    def start(self, stream_id: str) -> None:
        """Initialize state and bind this lifecycle to one opaque stream ID."""

        ...

    def update(self, request: TrackingRequest) -> TrackingResult:
        """Associate detections for one newer frame in the bound stream."""

        ...

    def reset(self) -> None:
        """Clear temporary identities while retaining the current stream binding."""

        ...

    def close(self) -> None:
        """Release tracker state; repeated calls must be safe."""

        ...


class TrackingPreview(Protocol):
    """Render one ephemeral local tracking view without owning pipeline state."""

    def show_tracking(
        self,
        frame: FramePacket,
        detections: FrameDetections,
        tracking: TrackingResult,
        detection_statistics: LiveDetectionStats,
        tracking_statistics: LiveTrackingStats,
    ) -> PreviewAction:
        """Render current tracking data and optionally request clean shutdown."""

        ...

    def close(self) -> None:
        """Release local preview resources; repeated calls must be safe."""

        ...


__all__ = ["LiveTracker", "TrackingPreview"]
