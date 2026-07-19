"""Composition of Phase 5.2 live detection with temporary identity tracking."""

from __future__ import annotations

from collections.abc import Callable
from time import monotonic

from hogflow.core import ConfigurationError, InputDataError
from hogflow.detection.inference import (
    FrameDetections,
    LiveDetectionStats,
    LiveInferenceConfiguration,
    PreviewAction,
)
from hogflow.detection.ports import LiveDetector
from hogflow.pipeline.live_detection_pipeline import LiveDetectionPipeline
from hogflow.streaming.lifecycle import LiveStreamRunner
from hogflow.streaming.models import FramePacket
from hogflow.tracking.errors import (
    MalformedTrackerOutputError,
    StaleTrackingRequestError,
    TemporaryTrackingError,
    TrackingError,
    TrackingPreviewError,
)
from hogflow.tracking.models import (
    LiveTrackingRunSummary,
    LiveTrackingSnapshot,
    TrackerMetadata,
    TrackingErrorCategory,
    TrackingRequest,
    TrackingResult,
)
from hogflow.tracking.ports import LiveTracker, TrackingPreview
from hogflow.tracking.telemetry import LiveTrackingTelemetry

_TrackingResultCallback = Callable[
    [FramePacket, FrameDetections, TrackingResult, LiveTrackingSnapshot], object
]
_TrackingStatisticsCallback = Callable[[LiveTrackingSnapshot], object]


class LiveTrackingPipeline:
    """Track successful Phase 5.2 detections without changing acquisition policy.

    The composed detection pipeline retains the Phase 5.1 fixed source buffer
    as the only backlog. Tracking runs serially in the detector result callback,
    so slow updates cannot create another queue. One tracker instance is bound
    to the pipeline's single source stream and is reset after camera reconnects.
    No counting, line crossing, session, storage, or permanent identity logic
    exists here.
    """

    def __init__(
        self,
        stream_runner: LiveStreamRunner,
        detector: LiveDetector,
        tracker: LiveTracker,
        inference_configuration: LiveInferenceConfiguration | None = None,
        *,
        preview: TrackingPreview | None = None,
        result_callback: _TrackingResultCallback | None = None,
        statistics_callback: _TrackingStatisticsCallback | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        self._stream_runner = stream_runner
        self._detector = detector
        self._tracker = tracker
        self._inference_configuration = inference_configuration or LiveInferenceConfiguration()
        self._preview = preview
        self._result_callback = result_callback
        self._statistics_callback = statistics_callback
        self._clock = monotonic_clock
        self._telemetry = LiveTrackingTelemetry()
        self._preview_active = preview is not None
        self._latest_detection_statistics: LiveDetectionStats | None = None
        self._last_reconnect_count = 0
        self._ran = False

    def run(
        self,
        *,
        maximum_frames: int | None = None,
        maximum_duration_seconds: float | None = None,
        statistics_interval_seconds: float | None = None,
    ) -> LiveTrackingRunSummary:
        """Run detection and tracking for one bounded or source-ended lifecycle."""

        if self._ran:
            raise ConfigurationError("Live tracking pipeline supports one lifecycle only.")
        self._ran = True
        source_id = self._stream_runner.health().identity.stream_id
        metadata: TrackerMetadata | None = None
        detection_summary = None
        pending_error: BaseException | None = None
        self._telemetry.record_starting()
        try:
            self._tracker.start(source_id)
            metadata = self._tracker.metadata
            self._telemetry.record_started()
            detection_pipeline = LiveDetectionPipeline(
                self._stream_runner,
                self._detector,
                self._inference_configuration,
                result_callback=self._handle_detection_result,
                statistics_callback=self._handle_detection_statistics,
                monotonic_clock=self._clock,
            )
            detection_summary = detection_pipeline.run(
                maximum_frames=maximum_frames,
                maximum_duration_seconds=maximum_duration_seconds,
                statistics_interval_seconds=statistics_interval_seconds,
            )
            self._latest_detection_statistics = detection_summary.statistics
        except BaseException as exc:
            if metadata is None:
                self._telemetry.record_lifecycle_failure(
                    TrackingErrorCategory.INITIALIZATION,
                    fatal=True,
                )
            pending_error = exc
        finally:
            self._close_preview_safely()
            if self._tracker.is_started:
                self._telemetry.record_stopping()
                try:
                    self._tracker.close()
                except BaseException as exc:
                    self._telemetry.record_lifecycle_failure(
                        TrackingErrorCategory.CLOSE,
                        fatal=True,
                    )
                    if pending_error is None:
                        pending_error = exc
                else:
                    self._telemetry.record_closed()

        if pending_error is not None:
            raise pending_error
        if detection_summary is None or metadata is None:
            raise MalformedTrackerOutputError(
                "Live tracking completed without detector or tracker summary data."
            )
        return LiveTrackingRunSummary(
            detection_summary=detection_summary,
            tracker=metadata,
            tracking_statistics=self._telemetry.snapshot(),
            tracker_closed=not self._tracker.is_started,
        )

    def statistics(self) -> LiveTrackingSnapshot:
        """Return current detector and tracker telemetry without frame history."""

        detection = self._latest_detection_statistics
        if detection is None:
            raise ConfigurationError("Detection statistics are unavailable before pipeline work.")
        return LiveTrackingSnapshot(detection=detection, tracking=self._telemetry.snapshot())

    def _handle_detection_result(
        self,
        frame: FramePacket,
        detections: FrameDetections,
        detection_statistics: LiveDetectionStats,
    ) -> PreviewAction | None:
        self._latest_detection_statistics = detection_statistics
        self._reset_after_reconnect_if_needed()
        request = TrackingRequest(
            source_id=detections.source_id,
            frame_sequence=detections.frame_sequence,
            captured_at=detections.captured_at,
            frame_width=detections.frame_width,
            frame_height=detections.frame_height,
            detections=detections.detections,
        )
        self._telemetry.record_request(request)
        try:
            tracking = self._tracker.update(request)
            self._validate_result(request, tracking)
        except TemporaryTrackingError:
            self._telemetry.record_failure(TrackingErrorCategory.UPDATE, fatal=False)
            return None
        except StaleTrackingRequestError:
            self._telemetry.record_failure(
                TrackingErrorCategory.STALE,
                fatal=True,
                stale=True,
            )
            raise
        except MalformedTrackerOutputError:
            self._telemetry.record_failure(
                TrackingErrorCategory.OUTPUT,
                fatal=True,
                malformed=True,
            )
            raise
        except InputDataError:
            self._telemetry.record_failure(
                TrackingErrorCategory.INPUT,
                fatal=True,
                malformed=True,
            )
            raise
        except TrackingError:
            self._telemetry.record_failure(TrackingErrorCategory.UPDATE, fatal=True)
            raise
        self._telemetry.record_success(tracking)
        snapshot = LiveTrackingSnapshot(
            detection=detection_statistics,
            tracking=self._telemetry.snapshot(),
        )
        if self._result_callback is not None:
            self._result_callback(frame, detections, tracking, snapshot)
        if self._preview_active and self._preview is not None:
            try:
                return self._preview.show_tracking(
                    frame,
                    detections,
                    tracking,
                    detection_statistics,
                    snapshot.tracking,
                )
            except TrackingPreviewError:
                self._telemetry.record_preview_failure()
                self._close_preview_safely()
                self._preview_active = False
        return None

    def _handle_detection_statistics(self, statistics: LiveDetectionStats) -> None:
        self._latest_detection_statistics = statistics
        if self._statistics_callback is not None:
            self._statistics_callback(
                LiveTrackingSnapshot(
                    detection=statistics,
                    tracking=self._telemetry.snapshot(),
                )
            )

    def _reset_after_reconnect_if_needed(self) -> None:
        reconnect_count = self._stream_runner.statistics().reconnect_count
        if reconnect_count <= self._last_reconnect_count:
            return
        try:
            self._tracker.reset()
        except TrackingError:
            self._telemetry.record_lifecycle_failure(
                TrackingErrorCategory.RESET,
                fatal=True,
            )
            raise
        self._telemetry.record_reset(reconnect=True)
        self._last_reconnect_count = reconnect_count

    @staticmethod
    def _validate_result(request: TrackingRequest, result: TrackingResult) -> None:
        if not isinstance(result, TrackingResult):
            raise MalformedTrackerOutputError(
                "Live tracker returned a framework-specific or unsupported result."
            )
        if (
            result.source_id != request.source_id
            or result.frame_sequence != request.frame_sequence
            or result.frame_width != request.frame_width
            or result.frame_height != request.frame_height
            or result.captured_at != request.captured_at
        ):
            raise MalformedTrackerOutputError(
                "Tracking result does not identify the exact detection frame."
            )

    def _close_preview_safely(self) -> None:
        if self._preview is None:
            return
        try:
            self._preview.close()
        except TrackingPreviewError:
            self._telemetry.record_preview_failure()


__all__ = ["LiveTrackingPipeline"]
