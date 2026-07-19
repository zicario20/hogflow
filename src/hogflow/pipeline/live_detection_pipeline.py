"""Bounded-latency orchestration from live stream packets to detections."""

from __future__ import annotations

from collections.abc import Callable
from math import isfinite
from time import monotonic

from hogflow.core import ConfigurationError
from hogflow.detection.errors import (
    DetectionPreviewError,
    FatalInferenceError,
    MalformedDetectorOutputError,
    TemporaryInferenceError,
)
from hogflow.detection.inference import (
    DetectionShutdownReason,
    FrameDetections,
    LiveDetectionRunSummary,
    LiveDetectionStats,
    LiveInferenceConfiguration,
    PreviewAction,
)
from hogflow.detection.ports import DetectionPreview, LiveDetector
from hogflow.detection.telemetry import LiveDetectionTelemetry
from hogflow.streaming.lifecycle import LiveStreamRunner
from hogflow.streaming.models import BufferReadStatus, FramePacket

_ResultCallback = Callable[[FramePacket, FrameDetections, LiveDetectionStats], object]
_StatisticsCallback = Callable[[LiveDetectionStats], object]


class LiveDetectionPipeline:
    """Consume the newest useful stream packet and run one detector serially.

    The Phase 5.1 acquisition thread remains independent from inference. The
    fixed source buffer is the only queue. Before each inference, all currently
    queued packets are drained and only the newest is retained; superseded,
    paced, every-N, and stale packets are counted as inference skips. Camera
    buffer overflow remains a separate source-drop counter.

    The pipeline owns detector and optional preview lifecycle for one run. It
    performs no tracking, counting, line crossing, recording, persistence, or
    remote transmission.
    """

    def __init__(
        self,
        stream_runner: LiveStreamRunner,
        detector: LiveDetector,
        configuration: LiveInferenceConfiguration | None = None,
        *,
        preview: DetectionPreview | None = None,
        result_callback: _ResultCallback | None = None,
        statistics_callback: _StatisticsCallback | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        self._stream_runner = stream_runner
        self._detector = detector
        self._configuration = configuration or LiveInferenceConfiguration()
        self._preview = preview
        self._result_callback = result_callback
        self._statistics_callback = statistics_callback
        self._clock = monotonic_clock
        self._telemetry = LiveDetectionTelemetry(
            self._configuration.latency_sample_capacity,
            monotonic_clock=monotonic_clock,
        )
        self._ran = False

    def run(
        self,
        *,
        maximum_frames: int | None = None,
        maximum_duration_seconds: float | None = None,
        statistics_interval_seconds: float | None = None,
    ) -> LiveDetectionRunSummary:
        """Run until source end, a configured bound, preview stop, or Ctrl+C."""

        if self._ran:
            raise ConfigurationError("Live detection pipeline supports one lifecycle only.")
        self._ran = True
        maximum_frames = _optional_positive_integer(maximum_frames, "maximum_frames")
        maximum_duration_seconds = _optional_positive_number(
            maximum_duration_seconds,
            "maximum_duration_seconds",
        )
        statistics_interval_seconds = _optional_positive_number(
            statistics_interval_seconds,
            "statistics_interval_seconds",
        )

        camera_started = False
        preview_active = self._preview is not None
        shutdown_reason = DetectionShutdownReason.SOURCE_CLOSED
        started_at = float(self._clock())
        next_statistics = (
            None
            if statistics_interval_seconds is None
            else started_at + statistics_interval_seconds
        )
        submitted = 0
        last_inference_started: float | None = None
        metadata = None
        pending_error: BaseException | None = None

        try:
            self._detector.load()
            metadata = self._detector.metadata
            self._stream_runner.start()
            camera_started = True
            try:
                while True:
                    now = float(self._clock())
                    if (
                        maximum_duration_seconds is not None
                        and now - started_at >= maximum_duration_seconds
                    ):
                        shutdown_reason = DetectionShutdownReason.MAXIMUM_DURATION
                        break

                    first = self._stream_runner.buffer.get(
                        self._configuration.buffer_poll_timeout_seconds
                    )
                    if first.status is BufferReadStatus.TIMEOUT:
                        next_statistics = self._publish_statistics_if_due(
                            now,
                            next_statistics,
                            statistics_interval_seconds,
                        )
                        continue
                    if first.status is BufferReadStatus.CLOSED:
                        self._stream_runner.join(5.0, raise_on_failure=True)
                        shutdown_reason = DetectionShutdownReason.SOURCE_CLOSED
                        break
                    if first.frame is None:
                        raise MalformedDetectorOutputError(
                            "A successful stream-buffer read omitted its frame."
                        )

                    remaining = None if maximum_frames is None else maximum_frames - submitted
                    packets = [first.frame]
                    while remaining is None or len(packets) < remaining:
                        additional = self._stream_runner.buffer.get(0.0)
                        if additional.status is not BufferReadStatus.FRAME:
                            break
                        if additional.frame is None:
                            raise MalformedDetectorOutputError(
                                "A successful stream-buffer read omitted its frame."
                            )
                        packets.append(additional.frame)

                    for packet in packets:
                        self._telemetry.record_submitted(self._frame_age_ms(packet))
                    submitted += len(packets)
                    if len(packets) > 1:
                        self._telemetry.record_skipped(len(packets) - 1)
                    frame = packets[-1]

                    should_infer, inference_started = self._should_infer(
                        frame,
                        last_inference_started,
                    )
                    if not should_infer:
                        self._telemetry.record_skipped()
                    else:
                        last_inference_started = inference_started
                        try:
                            result = self._detector.infer(frame)
                        except TemporaryInferenceError:
                            self._telemetry.record_failure()
                        except FatalInferenceError:
                            self._telemetry.record_failure()
                            raise
                        else:
                            try:
                                self._validate_result(frame, result)
                            except MalformedDetectorOutputError:
                                self._telemetry.record_failure()
                                raise
                            self._telemetry.record_inference(
                                result,
                                self._frame_age_ms(frame),
                            )
                            statistics = self.statistics()
                            if self._result_callback is not None:
                                self._result_callback(frame, result, statistics)
                            if preview_active and self._preview is not None:
                                try:
                                    action = self._preview.show(frame, result, statistics)
                                except DetectionPreviewError:
                                    self._telemetry.record_preview_failure()
                                    self._close_preview_safely()
                                    preview_active = False
                                else:
                                    if action is PreviewAction.STOP:
                                        shutdown_reason = DetectionShutdownReason.PREVIEW_REQUESTED
                                        break

                    now = float(self._clock())
                    next_statistics = self._publish_statistics_if_due(
                        now,
                        next_statistics,
                        statistics_interval_seconds,
                    )
                    if maximum_frames is not None and submitted >= maximum_frames:
                        shutdown_reason = DetectionShutdownReason.MAXIMUM_FRAMES
                        break
            except KeyboardInterrupt:
                shutdown_reason = DetectionShutdownReason.KEYBOARD_INTERRUPT
        except BaseException as exc:
            pending_error = exc
        finally:
            self._close_preview_safely()
            if camera_started:
                self._stream_runner.stop()
                try:
                    self._stream_runner.join(10.0, raise_on_failure=True)
                except BaseException as exc:
                    if pending_error is None:
                        pending_error = exc
            try:
                self._detector.close()
            except BaseException as exc:
                if pending_error is None:
                    pending_error = exc

        if pending_error is not None:
            raise pending_error
        if metadata is None:
            raise MalformedDetectorOutputError("Detector metadata was unavailable after loading.")
        return LiveDetectionRunSummary(
            source_id=self._stream_runner.health().identity.stream_id,
            source_type=self._stream_runner.health().identity.source_type,
            source_display_name=self._stream_runner.health().identity.display_name,
            detector=metadata,
            statistics=self.statistics(),
            shutdown_reason=shutdown_reason,
            final_camera_health=self._stream_runner.health().state,
            detector_closed=not self._detector.is_loaded,
            camera_released=not self._stream_runner.source_is_open(),
        )

    def statistics(self) -> LiveDetectionStats:
        """Return current detector telemetry merged with camera statistics."""

        return self._telemetry.snapshot(self._stream_runner.statistics())

    def _should_infer(
        self,
        frame: FramePacket,
        last_inference_started: float | None,
    ) -> tuple[bool, float]:
        now = float(self._clock())
        if frame.sequence_number % self._configuration.inference_every_n_frames != 0:
            return False, now
        target_fps = self._configuration.target_inference_fps
        if (
            target_fps is not None
            and last_inference_started is not None
            and now - last_inference_started < 1.0 / target_fps
        ):
            return False, now
        maximum_age = self._configuration.maximum_frame_age_ms
        if maximum_age is not None and self._frame_age_ms(frame, at_monotonic=now) > maximum_age:
            return False, now
        return True, now

    def _frame_age_ms(
        self,
        frame: FramePacket,
        *,
        at_monotonic: float | None = None,
    ) -> float:
        now = float(self._clock()) if at_monotonic is None else at_monotonic
        return max(0.0, now - frame.timestamp.monotonic_seconds) * 1000

    def _validate_result(self, frame: FramePacket, result: FrameDetections) -> None:
        if not isinstance(result, FrameDetections):
            raise MalformedDetectorOutputError(
                "Live detector returned a framework-specific or unsupported result."
            )
        if (
            result.source_id != frame.stream.stream_id
            or result.frame_sequence != frame.sequence_number
            or result.frame_width != frame.dimensions.width
            or result.frame_height != frame.dimensions.height
        ):
            raise MalformedDetectorOutputError(
                "Detector result does not identify the exact submitted source frame."
            )

    def _publish_statistics_if_due(
        self,
        now: float,
        next_statistics: float | None,
        interval: float | None,
    ) -> float | None:
        if next_statistics is not None and interval is not None and now >= next_statistics:
            if self._statistics_callback is not None:
                self._statistics_callback(self.statistics())
            return now + interval
        return next_statistics

    def _close_preview_safely(self) -> None:
        if self._preview is None:
            return
        try:
            self._preview.close()
        except DetectionPreviewError:
            self._telemetry.record_preview_failure()


def _optional_positive_integer(value: object | None, name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigurationError(f"{name} must be a positive integer when provided.")
    return value


def _optional_positive_number(value: object | None, name: str) -> float | None:
    if value is None:
        return None
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or float(value) <= 0
    ):
        raise ConfigurationError(f"{name} must be a positive number when provided.")
    return float(value)


__all__ = ["LiveDetectionPipeline"]
