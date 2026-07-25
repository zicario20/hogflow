"""Serial composition of live crossing with lifecycle directional counting."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from hogflow.core import ConfigurationError, InputDataError
from hogflow.counting.live_counting_errors import CountingPreviewError
from hogflow.counting.live_counting_models import (
    LiveCountingResult,
    LiveCountingRunSummary,
    LiveCountingSnapshot,
    LiveCountingStats,
)
from hogflow.counting.live_counting_ports import LiveDirectionalCounter
from hogflow.counting.live_models import (
    LiveCrossingResult,
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
from hogflow.pipeline.live_crossing_pipeline import LiveCrossingPipeline
from hogflow.streaming.lifecycle import LiveStreamRunner
from hogflow.streaming.models import FramePacket
from hogflow.tracking.models import LiveTrackingStats, TrackingResult
from hogflow.tracking.ports import LiveTracker

_CountingResultCallback = Callable[
    [
        FramePacket,
        FrameDetections,
        TrackingResult,
        LiveCrossingResult,
        LiveCountingResult,
        LiveCountingSnapshot,
    ],
    object,
]
_CountingStatisticsCallback = Callable[[LiveCountingSnapshot], object]


class CountingPreview(Protocol):
    """Render one ephemeral local counting diagnostic without session state."""

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
        """Render current lifecycle decisions and optionally request shutdown."""

        ...

    def close(self) -> None:
        """Release preview resources; repeated calls must be safe."""

        ...


class LiveCountingPipeline:
    """Apply Phase 7 decisions serially after each successful crossing result.

    Phase 5.1's fixed frame buffer remains the only queue. Crossing and
    counting execute serially in callbacks, preserving exact frame identity.
    A new crossing lifecycle triggers a fresh counting lifecycle before the
    first result after reconnect.
    """

    def __init__(
        self,
        stream_runner: LiveStreamRunner,
        detector: LiveDetector,
        tracker: LiveTracker,
        crossing_detector: LiveCrossingDetector,
        counter: LiveDirectionalCounter,
        inference_configuration: LiveInferenceConfiguration | None = None,
        *,
        preview: CountingPreview | None = None,
        result_callback: _CountingResultCallback | None = None,
        statistics_callback: _CountingStatisticsCallback | None = None,
    ) -> None:
        if not crossing_detector.configuration.enabled:
            raise ConfigurationError("Live counting pipeline requires enabled crossing.")
        if not counter.configuration.enabled:
            raise ConfigurationError("Live counting pipeline requires enabled counting.")
        if (
            counter.configuration.crossing_configuration_fingerprint
            != crossing_detector.configuration.fingerprint
        ):
            raise ConfigurationError(
                "Counting policy must reference the configured crossing fingerprint."
            )
        self._stream_runner = stream_runner
        self._detector = detector
        self._tracker = tracker
        self._crossing_detector = crossing_detector
        self._counter = counter
        self._inference_configuration = inference_configuration
        self._preview = preview
        self._result_callback = result_callback
        self._statistics_callback = statistics_callback
        self._preview_active = preview is not None
        self._ran = False

    def run(
        self,
        *,
        maximum_frames: int | None = None,
        maximum_duration_seconds: float | None = None,
        statistics_interval_seconds: float | None = None,
    ) -> LiveCountingRunSummary:
        """Run one source, crossing, and counting lifecycle composition."""

        if self._ran:
            raise ConfigurationError("Live counting pipeline supports one lifecycle only.")
        self._ran = True
        source_id = self._stream_runner.health().identity.stream_id
        crossing_summary = None
        pending_error: BaseException | None = None
        terminal_counting_lifecycle_id: str | None = None
        terminal_crossing_lifecycle_id: str | None = None
        try:
            self._crossing_detector.start(source_id)
            self._counter.start(source_id, self._crossing_detector.lifecycle_id)
            crossing_pipeline = LiveCrossingPipeline(
                self._stream_runner,
                self._detector,
                self._tracker,
                self._crossing_detector,
                self._inference_configuration,
                result_callback=self._handle_crossing_result,
                statistics_callback=self._handle_crossing_statistics,
            )
            crossing_summary = crossing_pipeline.run(
                maximum_frames=maximum_frames,
                maximum_duration_seconds=maximum_duration_seconds,
                statistics_interval_seconds=statistics_interval_seconds,
            )
        except BaseException as exc:
            pending_error = exc
        finally:
            self._close_preview_safely()
            if self._counter.is_started:
                terminal_counting_lifecycle_id = self._counter.counting_lifecycle_id
                terminal_crossing_lifecycle_id = self._counter.crossing_lifecycle_id
                try:
                    self._counter.close()
                except BaseException as exc:
                    if pending_error is None:
                        pending_error = exc

        if pending_error is not None:
            raise pending_error
        if crossing_summary is None:
            raise ConfigurationError("Live counting completed without a crossing summary.")
        if terminal_counting_lifecycle_id is None or terminal_crossing_lifecycle_id is None:
            raise ConfigurationError("Live counting completed without lifecycle provenance.")
        return LiveCountingRunSummary(
            source_id=source_id,
            counting_lifecycle_id=terminal_counting_lifecycle_id,
            crossing_lifecycle_id=terminal_crossing_lifecycle_id,
            crossing_summary=crossing_summary,
            counting_statistics=self._counter.statistics(),
            configuration_fingerprint=self._counter.configuration.fingerprint,
            counting_closed=not self._counter.is_started,
            limitations=(
                "Temporary tracker identities are not biological identities.",
                "Lifecycle totals are not session counts.",
                "Representative pig reverse and duplicate validation is pending.",
            ),
        )

    def _handle_crossing_result(
        self,
        frame: FramePacket,
        detections: FrameDetections,
        tracking: TrackingResult,
        crossing: LiveCrossingResult,
        crossing_snapshot: LiveCrossingSnapshot,
    ) -> PreviewAction | None:
        if crossing.crossing_lifecycle_id != self._counter.crossing_lifecycle_id:
            self._counter.reset(crossing.crossing_lifecycle_id)
        counting = self._counter.update(crossing)
        self._validate_result(crossing, counting)
        snapshot = LiveCountingSnapshot(
            source_id=self._counter.source_id,
            counting_lifecycle_id=self._counter.counting_lifecycle_id,
            crossing_lifecycle_id=self._counter.crossing_lifecycle_id,
            crossing=crossing_snapshot,
            counting=self._counter.statistics(),
        )
        if self._result_callback is not None:
            action = self._result_callback(
                frame,
                detections,
                tracking,
                crossing,
                counting,
                snapshot,
            )
            if action is PreviewAction.STOP:
                return PreviewAction.STOP
        if self._preview_active and self._preview is not None:
            try:
                return self._preview.show_counting(
                    frame,
                    detections,
                    tracking,
                    crossing,
                    counting,
                    crossing_snapshot.tracking.detection,
                    crossing_snapshot.tracking.tracking,
                    crossing_snapshot.crossing,
                    snapshot.counting,
                )
            except CountingPreviewError:
                self._counter.record_preview_failure()
                self._close_preview_safely()
                self._preview_active = False
        return None

    def _handle_crossing_statistics(self, snapshot: LiveCrossingSnapshot) -> None:
        if self._statistics_callback is not None:
            self._statistics_callback(
                LiveCountingSnapshot(
                    source_id=self._counter.source_id,
                    counting_lifecycle_id=self._counter.counting_lifecycle_id,
                    crossing_lifecycle_id=self._counter.crossing_lifecycle_id,
                    crossing=snapshot,
                    counting=self._counter.statistics(),
                )
            )

    @staticmethod
    def _validate_result(
        crossing: LiveCrossingResult,
        counting: LiveCountingResult,
    ) -> None:
        if not isinstance(counting, LiveCountingResult):
            raise InputDataError("Directional counter returned an unsupported result.")
        if (
            counting.source_id != crossing.source_id
            or counting.crossing_lifecycle_id != crossing.crossing_lifecycle_id
            or counting.frame_sequence != crossing.frame_sequence
            or counting.captured_at != crossing.captured_at
        ):
            raise InputDataError("Counting result does not identify the exact crossing frame.")

    def _close_preview_safely(self) -> None:
        if self._preview is None:
            return
        try:
            self._preview.close()
        except CountingPreviewError:
            self._counter.record_preview_failure()


__all__ = ["CountingPreview", "LiveCountingPipeline"]
