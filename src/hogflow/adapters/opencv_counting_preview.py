"""Optional local-only OpenCV preview for Phase 7 counting diagnostics."""

from __future__ import annotations

from types import ModuleType
from typing import Any

from hogflow.adapters.opencv_crossing_preview import OpenCVCrossingPreview
from hogflow.counting.live_counting_errors import CountingPreviewError
from hogflow.counting.live_counting_models import (
    LiveCountingConfiguration,
    LiveCountingResult,
    LiveCountingStats,
)
from hogflow.counting.live_errors import CrossingPreviewError
from hogflow.counting.live_models import (
    LiveCrossingConfiguration,
    LiveCrossingResult,
    LiveCrossingStats,
)
from hogflow.detection.inference import FrameDetections, LiveDetectionStats, PreviewAction
from hogflow.streaming.models import FramePacket
from hogflow.tracking.models import LiveTrackingStats, TrackingResult


class OpenCVCountingPreview(OpenCVCrossingPreview):
    """Render ephemeral crossing and lifecycle-count diagnostics.

    The adapter does not decide, persist, or correct counts. It renders the
    immutable result supplied by the Phase 7 domain pipeline.
    """

    def __init__(
        self,
        crossing_configuration: LiveCrossingConfiguration,
        counting_configuration: LiveCountingConfiguration,
        window_name: str = "HogFlow live lifecycle counting",
        *,
        show_track_ids: bool = True,
        cv2_module: ModuleType | Any | None = None,
        numpy_module: ModuleType | Any | None = None,
    ) -> None:
        if not isinstance(counting_configuration, LiveCountingConfiguration):
            raise CountingPreviewError("Counting preview requires valid configuration.")
        if not counting_configuration.enabled:
            raise CountingPreviewError("Counting preview requires enabled counting.")
        super().__init__(
            crossing_configuration,
            window_name,
            show_track_ids=show_track_ids,
            cv2_module=cv2_module,
            numpy_module=numpy_module,
        )
        self._counting_configuration = counting_configuration
        self._current_counting: LiveCountingResult | None = None

    def show_counting(
        self,
        frame: FramePacket,
        detections: FrameDetections,
        tracking: TrackingResult,
        crossing: LiveCrossingResult,
        counting: LiveCountingResult,
        detection_statistics: LiveDetectionStats,
        tracking_statistics: LiveTrackingStats,
        crossing_statistics: LiveCrossingStats,
        counting_statistics: LiveCountingStats,
    ) -> PreviewAction:
        """Render one current result without retaining decision history."""

        del counting_statistics
        if not isinstance(counting, LiveCountingResult):
            raise CountingPreviewError("Counting preview requires LiveCountingResult.")
        self._current_counting = counting
        try:
            return super().show_crossing(
                frame,
                detections,
                tracking,
                crossing,
                detection_statistics,
                tracking_statistics,
                crossing_statistics,
            )
        except CrossingPreviewError:
            raise CountingPreviewError("Local OpenCV counting preview failed.") from None
        finally:
            self._current_counting = None

    def _additional_diagnostic_lines(self) -> tuple[str, ...]:
        counting = self._current_counting
        if counting is None:
            return ()
        latest = "decision=none"
        if counting.decisions:
            decision = counting.decisions[-1]
            latest = f"decision={decision.decision_type.value} tracker_id={decision.tracker_id}"
        positive = self._counting_configuration.positive_direction
        return (
            f"Lifecycle count={counting.lifecycle_directional_count}",
            latest,
            (
                f"positive_direction={positive.value if positive is not None else 'unknown'} "
                f"lifecycle={counting.counting_lifecycle_id}"
            ),
        )

    def close(self) -> None:
        """Destroy the local window and sanitize expected preview failures."""

        try:
            super().close()
        except CrossingPreviewError:
            raise CountingPreviewError("Local OpenCV counting preview cleanup failed.") from None


__all__ = ["OpenCVCountingPreview"]
