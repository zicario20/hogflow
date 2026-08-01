"""Small public ports consumed by the production runtime supervisor."""

from __future__ import annotations

from typing import Protocol

from hogflow.camera import CountingPipelineSnapshot, PreviewSnapshot
from hogflow.runtime.models import ProcessMemorySnapshot
from hogflow.sessions import MultiDockRuntimeSnapshot


class SupervisedCountingPipeline(Protocol):
    """Public operations required from the existing one-worker controller."""

    def snapshot(self) -> CountingPipelineSnapshot:
        """Return immutable one-worker state."""

    def preview_snapshot(self) -> PreviewSnapshot:
        """Return bounded optional-preview state."""

    def restart(self) -> CountingPipelineSnapshot:
        """Recreate and start the configured source and worker."""

    def restart_preview(self) -> PreviewSnapshot:
        """Reset only optional visual state."""


class SupervisedRuntimeAccess(Protocol):
    """Read the authoritative shared-lane runtime through its serialization boundary."""

    def snapshot(self) -> MultiDockRuntimeSnapshot:
        """Return one immutable four-dock and lane snapshot."""


class ProcessMemoryProbe(Protocol):
    """Return one process-memory sample without retaining allocation history."""

    def snapshot(self) -> ProcessMemorySnapshot:
        """Capture current and peak resident memory when available."""


__all__ = [
    "ProcessMemoryProbe",
    "SupervisedCountingPipeline",
    "SupervisedRuntimeAccess",
]
