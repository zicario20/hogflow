"""Small framework-neutral behavior contracts for live inference."""

from __future__ import annotations

from typing import Protocol

from hogflow.detection.inference import (
    FrameDetections,
    LiveDetectionStats,
    ModelArtifactMetadata,
    PreviewAction,
)
from hogflow.streaming.models import FramePacket


class LiveDetector(Protocol):
    """Load, infer, and close one reusable detector behind a stable boundary.

    Implementations own model resources and framework conversion. ``infer`` is
    called serially by Phase 5.2 and receives exactly one immutable stream
    packet. Implementations make no thread-safety guarantee and must not expose
    framework objects, hidden global model state, tracking, or counting.
    """

    @property
    def metadata(self) -> ModelArtifactMetadata:
        """Return sanitized model metadata after successful loading."""

        ...

    @property
    def is_loaded(self) -> bool:
        """Return whether inference resources are currently available."""

        ...

    def load(self) -> None:
        """Load and validate local inference resources explicitly."""

        ...

    def infer(self, frame: FramePacket) -> FrameDetections:
        """Return immutable detections tied to exactly one source frame."""

        ...

    def close(self) -> None:
        """Release detector resources; repeated calls must be safe."""

        ...


class DetectionPreview(Protocol):
    """Render one local ephemeral preview without owning pipeline state."""

    def show(
        self,
        frame: FramePacket,
        detections: FrameDetections,
        statistics: LiveDetectionStats,
    ) -> PreviewAction:
        """Render current data and optionally request cooperative shutdown."""

        ...

    def close(self) -> None:
        """Release local preview resources; repeated calls must be safe."""

        ...


__all__ = ["DetectionPreview", "LiveDetector"]
