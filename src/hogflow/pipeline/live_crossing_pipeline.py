"""Serial composition of live tracking with virtual-line crossing events."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from hogflow.core import ConfigurationError, InputDataError
from hogflow.counting.live_errors import CrossingPreviewError
from hogflow.counting.live_models import (
    LiveCrossingResult,
    LiveCrossingRunSummary,
    LiveCrossingSnapshot,
    LiveCrossingStats,
)
from hogflow.counting.live_ports import LiveCrossingDetector
from hogflow.detection.inference import (
    FrameDetections,
    LiveDetectionStats,
    LiveInferenceConfiguration,
    PreviewAction,
)
from hogflow.detection.ports import LiveDetector
from hogflow.pipeline.live_tracking_pipeline import LiveTrackingPipeline
from hogflow.streaming.lifecycle import LiveStreamRunner
from hogflow.streaming.models import FramePacket
from hogflow.tracking.models import LiveTrackingSnapshot, LiveTrackingStats, TrackingResult
from hogflow.tracking.ports import LiveTracker

_CrossingResultCallback = Callable[
    [FramePacket, FrameDetections, TrackingResult, LiveCrossingResult, LiveCrossingSnapshot],
    object,
]
_CrossingStatisticsCallback = Callable[[LiveCrossingSnapshot], object]


class CrossingPreview(Protocol):
    """Render one ephemeral local crossing view without business state."""

    def show_crossing(
        self,
        frame: FramePacket,
        detections: FrameDetections,
        tracking: TrackingResult,
        crossing: LiveCrossingResult,
        detection_statistics: LiveDetectionStats,
        tracking_statistics: LiveTrackingStats,
        crossing_statistics: LiveCrossingStats,
    ) -> PreviewAction:
        """Render current geometry and optionally request clean shutdown."""

        ...

    def close(self) -> None:
        """Release preview resources; repeated calls must be safe."""

        ...


class LiveCrossingPipeline:
    """Emit crossing events serially after successful live tracking.

    The composed Phase 5.3 pipeline retains the Phase 5.1 source buffer as the
    only queue. Crossing runs in the tracking result callback and therefore
    cannot be applied to the wrong frame or create another backlog. Tracker
    reconnect resets are mirrored before the next successful crossing update.
    """

    def __init__(
        self,
        stream_runner: LiveStreamRunner,
        detector: LiveDetector,
        tracker: LiveTracker,
        crossing_detector: LiveCrossingDetector,
        inference_configuration: LiveInferenceConfiguration | None = None,
        *,
        preview: CrossingPreview | None = None,
        result_callback: _CrossingResultCallback | None = None,
        statistics_callback: _CrossingStatisticsCallback | None = None,
    ) -> None:
        if not crossing_detector.configuration.enabled:
            raise ConfigurationError("Live crossing pipeline requires enabled crossing.")
        self._stream_runner = stream_runner
        self._detector = detector
        self._tracker = tracker
        self._crossing_detector = crossing_detector
        self._inference_configuration = inference_configuration
        self._preview = preview
        self._result_callback = result_callback
        self._statistics_callback = statistics_callback
        self._preview_active = preview is not None
        self._last_tracker_restart_count = 0
        self._latest_tracking_snapshot: LiveTrackingSnapshot | None = None
        self._ran = False

    def run(
        self,
        *,
        maximum_frames: int | None = None,
        maximum_duration_seconds: float | None = None,
        statistics_interval_seconds: float | None = None,
    ) -> LiveCrossingRunSummary:
        """Run one source/tracker/crossing lifecycle."""

        if self._ran:
            raise ConfigurationError("Live crossing pipeline supports one lifecycle only.")
        self._ran = True
        source_id = self._stream_runner.health().identity.stream_id
        tracking_summary = None
        pending_error: BaseException | None = None
        try:
            self._crossing_detector.start(source_id)
            tracking_pipeline = LiveTrackingPipeline(
                self._stream_runner,
                self._detector,
                self._tracker,
                self._inference_configuration,
                result_callback=self._handle_tracking_result,
                statistics_callback=self._handle_tracking_statistics,
            )
            tracking_summary = tracking_pipeline.run(
                maximum_frames=maximum_frames,
                maximum_duration_seconds=maximum_duration_seconds,
                statistics_interval_seconds=statistics_interval_seconds,
            )
        except BaseException as exc:
            pending_error = exc
        finally:
            self._close_preview_safely()
            if self._crossing_detector.is_started:
                try:
                    self._crossing_detector.close()
                except BaseException as exc:
                    if pending_error is None:
                        pending_error = exc

        if pending_error is not None:
            raise pending_error
        if tracking_summary is None:
            raise ConfigurationError("Live crossing completed without a tracking summary.")
        return LiveCrossingRunSummary(
            tracking_summary=tracking_summary,
            crossing_statistics=self._crossing_detector.statistics(),
            configuration_fingerprint=self._crossing_detector.configuration.fingerprint,
            crossing_closed=not self._crossing_detector.is_started,
        )

    def _handle_tracking_result(
        self,
        frame: FramePacket,
        detections: FrameDetections,
        tracking: TrackingResult,
        tracking_snapshot: LiveTrackingSnapshot,
    ) -> PreviewAction | None:
        self._latest_tracking_snapshot = tracking_snapshot
        restart_count = tracking_snapshot.tracking.tracker_restarts
        while self._last_tracker_restart_count < restart_count:
            self._crossing_detector.reset()
            self._last_tracker_restart_count += 1
        crossing = self._crossing_detector.update(tracking)
        self._validate_result(tracking, crossing)
        snapshot = LiveCrossingSnapshot(
            tracking=tracking_snapshot,
            crossing=self._crossing_detector.statistics(),
        )
        if self._result_callback is not None:
            action = self._result_callback(frame, detections, tracking, crossing, snapshot)
            if action is PreviewAction.STOP:
                return PreviewAction.STOP
        if self._preview_active and self._preview is not None:
            try:
                return self._preview.show_crossing(
                    frame,
                    detections,
                    tracking,
                    crossing,
                    tracking_snapshot.detection,
                    tracking_snapshot.tracking,
                    snapshot.crossing,
                )
            except CrossingPreviewError:
                self._crossing_detector.record_preview_failure()
                self._close_preview_safely()
                self._preview_active = False
        return None

    def _handle_tracking_statistics(self, snapshot: LiveTrackingSnapshot) -> None:
        self._latest_tracking_snapshot = snapshot
        if self._statistics_callback is not None:
            self._statistics_callback(
                LiveCrossingSnapshot(
                    tracking=snapshot,
                    crossing=self._crossing_detector.statistics(),
                )
            )

    @staticmethod
    def _validate_result(tracking: TrackingResult, crossing: LiveCrossingResult) -> None:
        if not isinstance(crossing, LiveCrossingResult):
            raise InputDataError("Crossing detector returned an unsupported result.")
        if (
            crossing.source_id != tracking.source_id
            or crossing.frame_sequence != tracking.frame_sequence
            or crossing.captured_at != tracking.captured_at
        ):
            raise InputDataError("Crossing result does not identify the exact tracking frame.")

    def _close_preview_safely(self) -> None:
        if self._preview is None:
            return
        try:
            self._preview.close()
        except CrossingPreviewError:
            self._crossing_detector.record_preview_failure()


__all__ = ["CrossingPreview", "LiveCrossingPipeline"]
