"""Framework-neutral ports for controlled local validation orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from hogflow.data import VideoFileMetadata
from hogflow.validation.models import CalibrationCandidate, VideoValidationResult


class VideoMetadataInspector(Protocol):
    """Read bounded metadata without retaining video frames."""

    def inspect(self, path: str | Path, *, relative_path: str | Path) -> VideoFileMetadata:
        """Return immutable metadata for one exact local video."""

        ...


class ModelPresentValidationBackend(Protocol):
    """Execute one candidate through existing public pipeline boundaries.

    Local paths are ephemeral composition inputs. Implementations must never
    place them in the returned path-free result.
    """

    def run(
        self,
        *,
        video_path: Path,
        model_path: Path,
        candidate: CalibrationCandidate,
        manual_total: int | None,
    ) -> VideoValidationResult:
        """Run one isolated candidate and return bounded aggregate evidence."""

        ...


__all__ = ["ModelPresentValidationBackend", "VideoMetadataInspector"]
