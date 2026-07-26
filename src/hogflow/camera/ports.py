"""Framework-neutral ports for the Phase 9.3–9.4 shared camera worker."""

from __future__ import annotations

from typing import Protocol

from hogflow.camera.models import ActiveCountingBinding
from hogflow.camera.preview_models import PreviewFrame
from hogflow.counting import LiveCrossingResult
from hogflow.streaming import CameraSource, FramePacket, StreamConfiguration


class CountingFrameProcessor(Protocol):
    """Run detector, tracker, and optional crossing work for one frame."""

    @property
    def is_started(self) -> bool:
        """Return whether detector/tracker resources are active."""

    def start(self, source_id: str) -> None:
        """Load resources and bind processing to one sanitized source."""

    def process(
        self,
        frame: FramePacket,
        crossing_lifecycle_id: str | None,
    ) -> LiveCrossingResult | None:
        """Return crossing evidence only for an active lifecycle."""

    def reset(self) -> None:
        """Clear tracker/crossing state after one live-source reconnection."""

    def close(self) -> None:
        """Release detector, tracker, and crossing resources safely."""


class VideoSourceFactory(Protocol):
    """Create one unopened source from immutable configuration."""

    def __call__(self, configuration: StreamConfiguration) -> CameraSource:
        """Return one explicit source adapter without opening it."""


class CountingFrameProcessorFactory(Protocol):
    """Create one fresh processor for one pipeline start."""

    def __call__(self) -> CountingFrameProcessor:
        """Return a processor that has not started."""


class PreviewFramePublisher(Protocol):
    """Non-blocking publication port for optional visual diagnostics."""

    def publish(self, frame: PreviewFrame) -> None:
        """Replace the current visual frame without waiting for the UI."""

    def record_publication_failure(self) -> None:
        """Record one isolated preview preparation/publication failure."""


class SharedCountingRuntimeAccess(Protocol):
    """Serialized access to the one Phase 8 shared counting lane."""

    @property
    def source_id(self) -> str:
        """Return the lane's one configured source identity."""

    def active_binding(self) -> ActiveCountingBinding | None:
        """Return current immutable lane ownership."""

    def route_crossing(
        self,
        expected_binding: ActiveCountingBinding,
        result: LiveCrossingResult,
    ) -> None:
        """Route evidence only if the expected binding still owns the lane."""


__all__ = [
    "CountingFrameProcessor",
    "CountingFrameProcessorFactory",
    "PreviewFramePublisher",
    "SharedCountingRuntimeAccess",
    "VideoSourceFactory",
]
