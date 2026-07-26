"""One controlled worker for the shared source and counting pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Event, RLock, Thread
from time import monotonic
from typing import Callable

from hogflow.camera.errors import (
    CameraPipelineConfigurationError,
    CameraPipelineLifecycleError,
    CameraPipelineProcessingError,
    CameraPipelineShutdownError,
    StaleCameraEvidenceError,
)
from hogflow.camera.models import (
    CameraRecoveryConfiguration,
    CameraSnapshot,
    CameraStatus,
    CountingPipelineSnapshot,
    CountingPipelineStatus,
    PipelineFailureCategory,
)
from hogflow.camera.ports import (
    CountingFrameProcessor,
    CountingFrameProcessorFactory,
    SharedCountingRuntimeAccess,
    VideoSourceFactory,
)
from hogflow.camera.preview_channel import LatestPreviewFrameChannel
from hogflow.camera.preview_models import PreviewConfiguration, PreviewFrame, PreviewSnapshot
from hogflow.counting import LiveCrossingError
from hogflow.detection import (
    DetectionInferenceError,
    DetectorLoadError,
    TemporaryInferenceError,
)
from hogflow.streaming import (
    CameraSource,
    FramePacket,
    FrameTimestamp,
    SourceType,
    StreamConfiguration,
    StreamReadStatus,
)
from hogflow.streaming.errors import StreamFatalReadError, StreamOpenError
from hogflow.tracking import TemporaryTrackingError, TrackingError

Clock = Callable[[], datetime]


class CountingPipelineController:
    """Own one source, one processor, and one shared worker lifecycle.

    The worker performs acquisition and detector/tracker/crossing processing
    serially and retains at most one frame. It never calls presentation code.
    Phase 8 mutations pass through ``SharedCountingRuntimeAccess``, whose one
    lock also serializes operator commands and immutable snapshot reads.
    """

    def __init__(
        self,
        runtime: SharedCountingRuntimeAccess,
        source_factory: VideoSourceFactory,
        processor_factory: CountingFrameProcessorFactory,
        *,
        clock: Clock | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
        worker_join_timeout_seconds: float = 5.0,
        startup_wait_seconds: float = 1.0,
        recovery_configuration: CameraRecoveryConfiguration = CameraRecoveryConfiguration(),
        preview_channel: LatestPreviewFrameChannel | None = None,
    ) -> None:
        if not callable(source_factory) or not callable(processor_factory):
            raise TypeError("Camera pipeline factories must be callable.")
        for value, label in (
            (worker_join_timeout_seconds, "worker join timeout"),
            (startup_wait_seconds, "startup wait"),
        ):
            if not isinstance(value, (int, float)) or isinstance(value, bool) or float(value) <= 0:
                raise CameraPipelineConfigurationError(f"Camera pipeline {label} must be positive.")
        if not isinstance(recovery_configuration, CameraRecoveryConfiguration):
            raise CameraPipelineConfigurationError(
                "Camera pipeline recovery configuration is invalid."
            )
        self._runtime = runtime
        self._source_factory = source_factory
        self._processor_factory = processor_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._monotonic = monotonic_clock
        self._join_timeout = float(worker_join_timeout_seconds)
        self._startup_wait = float(startup_wait_seconds)
        self._recovery_configuration = recovery_configuration
        self._preview = preview_channel or LatestPreviewFrameChannel(
            PreviewConfiguration(enabled=False),
            monotonic_clock=monotonic_clock,
        )
        self._lock = RLock()
        self._stop_requested = Event()
        self._startup_complete = Event()
        self._source: CameraSource | None = None
        self._processor: CountingFrameProcessor | None = None
        self._configuration: StreamConfiguration | None = None
        self._worker: Thread | None = None
        self._camera_status = CameraStatus.NOT_CONFIGURED
        self._pipeline_status = CountingPipelineStatus.STOPPED
        self._frames_acquired = 0
        self._frames_processed = 0
        self._temporary_processing_failures = 0
        self._stale_results_rejected = 0
        self._last_frame_index: int | None = None
        self._last_successful_frame_at: datetime | None = None
        self._source_exhausted = False
        self._failure_category = PipelineFailureCategory.NONE
        self._failure_message: str | None = None
        self._started_at: datetime | None = None
        self._stopped_at: datetime | None = None
        self._first_frame_monotonic: float | None = None
        self._last_frame_monotonic: float | None = None
        self._recovery_attempts = 0
        self._recovery_successes = 0

    def configure(self, configuration: StreamConfiguration) -> CountingPipelineSnapshot:
        """Configure one unopened camera or local-file source."""

        if not isinstance(configuration, StreamConfiguration):
            raise CameraPipelineConfigurationError(
                "Video source configuration must use the streaming contract."
            )
        if configuration.source_type not in (SourceType.USB, SourceType.FILE):
            raise CameraPipelineConfigurationError(
                "Operator camera integration supports USB or local-file sources."
            )
        if configuration.stream_id != self._runtime.source_id:
            raise CameraPipelineConfigurationError(
                "Configured source identity must match the shared counting lane."
            )
        with self._lock:
            if self._worker_is_alive() or self._pipeline_status in (
                CountingPipelineStatus.STARTING,
                CountingPipelineStatus.RUNNING,
                CountingPipelineStatus.STOPPING,
            ):
                raise CameraPipelineLifecycleError(
                    "Stop the counting pipeline before changing its source."
                )
        try:
            prospective_source = self._source_factory(configuration)
        except Exception as exc:
            raise CameraPipelineConfigurationError(
                "Configured video source is unavailable or invalid."
            ) from exc
        with self._lock:
            self._close_configured_source()
            self._configuration = configuration
            self._source = prospective_source
            self._processor = None
            self._worker = None
            self._camera_status = CameraStatus.CLOSED
            self._pipeline_status = CountingPipelineStatus.STOPPED
            self._reset_run_metrics()
            self._preview.reset()
            return self._snapshot_locked()

    def configure_camera(self, camera_index: int) -> CountingPipelineSnapshot:
        """Configure the shared lane's local camera index without opening it."""

        return self.configure(StreamConfiguration.usb(self._runtime.source_id, camera_index))

    def configure_file(self, path: str | Path) -> CountingPipelineSnapshot:
        """Configure one local video file without exposing its path in snapshots."""

        return self.configure(StreamConfiguration.file(self._runtime.source_id, path))

    def start(self) -> CountingPipelineSnapshot:
        """Start the single non-daemon camera worker."""

        with self._lock:
            if self._worker_is_alive() or self._pipeline_status in (
                CountingPipelineStatus.STARTING,
                CountingPipelineStatus.RUNNING,
                CountingPipelineStatus.STOPPING,
            ):
                raise CameraPipelineLifecycleError("Counting pipeline is already active.")
            if self._source is None or self._configuration is None:
                raise CameraPipelineLifecycleError(
                    "Configure a video source before starting the counting pipeline."
                )
            if self._pipeline_status is CountingPipelineStatus.FAILED:
                raise CameraPipelineLifecycleError(
                    "Reconfigure the source before restarting a failed pipeline."
                )
            try:
                processor = self._processor_factory()
            except Exception as exc:
                raise CameraPipelineConfigurationError(
                    "Counting frame processor could not be created."
                ) from exc
            self._processor = processor
            self._stop_requested.clear()
            self._startup_complete.clear()
            self._pipeline_status = CountingPipelineStatus.STARTING
            self._camera_status = CameraStatus.OPENING
            self._failure_category = PipelineFailureCategory.NONE
            self._failure_message = None
            self._source_exhausted = False
            self._preview.reset()
            self._started_at = self._clock()
            self._stopped_at = None
            worker = Thread(
                target=self._run_worker,
                name="hogflow-shared-counting-pipeline",
                daemon=False,
            )
            self._worker = worker
            worker.start()
        self._startup_complete.wait(self._startup_wait)
        return self.snapshot()

    def stop(self) -> CountingPipelineSnapshot:
        """Request shutdown, release the source, and join the sole worker."""

        with self._lock:
            worker = self._worker
            if worker is None or not worker.is_alive():
                self._preview.clear()
                return self._snapshot_locked()
            self._pipeline_status = CountingPipelineStatus.STOPPING
            self._stop_requested.set()
            source = self._source
        if source is not None and source.is_open():
            try:
                source.close()
            except Exception as exc:
                with self._lock:
                    self._record_failure(
                        PipelineFailureCategory.SHUTDOWN,
                        "Configured video source could not close cleanly.",
                    )
                raise CameraPipelineShutdownError(
                    "Configured video source could not close cleanly."
                ) from exc
        worker.join(self._join_timeout)
        if worker.is_alive():
            with self._lock:
                self._record_failure(
                    PipelineFailureCategory.SHUTDOWN,
                    "Counting pipeline worker did not stop within the configured timeout.",
                )
            raise CameraPipelineShutdownError(
                "Counting pipeline worker did not stop within the configured timeout."
            )
        self._preview.clear()
        return self.snapshot()

    def close(self) -> CountingPipelineSnapshot:
        """Stop acquisition and permanently close the optional visual channel."""

        snapshot = self.stop()
        self._preview.close()
        return snapshot

    def snapshot(self) -> CountingPipelineSnapshot:
        """Return one immutable bounded camera/pipeline projection."""

        with self._lock:
            return self._snapshot_locked()

    def latest_preview_frame(self) -> PreviewFrame | None:
        """Return and remove the newest visual frame without blocking the worker."""

        return self._preview.take_latest()

    def preview_snapshot(self) -> PreviewSnapshot:
        """Return bounded visual-channel telemetry without pixel data."""

        return self._preview.snapshot()

    def record_preview_render_failure(self) -> PreviewSnapshot:
        """Disable a failed renderer while leaving camera/counting work unchanged."""

        return self._preview.record_render_failure()

    def _run_worker(self) -> None:
        source = self._source
        processor = self._processor
        if source is None or processor is None:
            with self._lock:
                self._record_failure(
                    PipelineFailureCategory.LIFECYCLE,
                    "Counting pipeline started without configured resources.",
                )
                self._startup_complete.set()
            return
        ended = False
        failure: tuple[PipelineFailureCategory, str] | None = None
        try:
            if not self._open_source(source):
                return
            processor.start(source.identity.stream_id)
            with self._lock:
                self._camera_status = CameraStatus.RUNNING
                self._pipeline_status = CountingPipelineStatus.RUNNING
                self._startup_complete.set()
            sequence = 0
            temporary_source_failures = 0
            while not self._stop_requested.is_set():
                try:
                    result = source.read()
                except StreamFatalReadError:
                    if self._recover_source(source, processor):
                        temporary_source_failures = 0
                        continue
                    if self._stop_requested.is_set():
                        break
                    raise
                if result.status is StreamReadStatus.FRAME:
                    if result.frame is None:
                        raise StreamFatalReadError(
                            "Video source returned a frame status without frame data."
                        )
                    acquired_at = self._clock()
                    packet = FramePacket(
                        stream=source.identity,
                        sequence_number=sequence,
                        timestamp=FrameTimestamp(
                            acquired_at=acquired_at,
                            monotonic_seconds=float(self._monotonic()),
                            source_seconds=result.frame.source_timestamp_seconds,
                        ),
                        dimensions=result.frame.dimensions,
                        payload=result.frame.payload,
                    )
                    with self._lock:
                        self._frames_acquired += 1
                        self._last_frame_index = sequence
                        self._last_successful_frame_at = acquired_at
                        self._camera_status = CameraStatus.RUNNING
                        self._record_frame_timing(packet.timestamp.monotonic_seconds)
                    temporary_source_failures = 0
                    binding = self._runtime.active_binding()
                    lifecycle_id = None if binding is None else binding.crossing_lifecycle_id
                    try:
                        crossing = processor.process(packet, lifecycle_id)
                    except (TemporaryInferenceError, TemporaryTrackingError):
                        with self._lock:
                            self._frames_processed += 1
                            self._temporary_processing_failures += 1
                        sequence += 1
                        continue
                    with self._lock:
                        self._frames_processed += 1
                    if crossing is not None and binding is not None:
                        try:
                            self._runtime.route_crossing(binding, crossing)
                        except StaleCameraEvidenceError:
                            with self._lock:
                                self._stale_results_rejected += 1
                        sequence += 1
                        continue
                    sequence += 1
                    continue
                if result.status is StreamReadStatus.TEMPORARY_UNAVAILABLE:
                    temporary_source_failures += 1
                    with self._lock:
                        self._camera_status = CameraStatus.DISCONNECTED
                    threshold = self._recovery_configuration.temporary_failures_before_reopen
                    if (
                        self._recovery_configuration.enabled
                        and source.is_live
                        and temporary_source_failures >= threshold
                    ):
                        if self._recover_source(source, processor):
                            temporary_source_failures = 0
                            continue
                        if self._stop_requested.is_set():
                            break
                        raise StreamFatalReadError(
                            "Live video source exhausted bounded recovery attempts."
                        )
                    self._stop_requested.wait(result.retry_after_seconds)
                    continue
                if result.status is StreamReadStatus.END_OF_STREAM:
                    ended = True
                    break
                if result.status is StreamReadStatus.STOPPED and self._stop_requested.is_set():
                    break
                if result.status is StreamReadStatus.STOPPED and self._recover_source(
                    source,
                    processor,
                ):
                    temporary_source_failures = 0
                    continue
                raise StreamFatalReadError("Video source stopped or was interrupted unexpectedly.")
        except Exception as exc:
            if not (self._stop_requested.is_set() and isinstance(exc, StreamFatalReadError)):
                failure = _failure_for(exc)
        finally:
            self._startup_complete.set()
            cleanup_failure: BaseException | None = None
            try:
                processor.close()
            except BaseException as exc:
                cleanup_failure = exc
            try:
                if source.is_open():
                    source.close()
            except BaseException as exc:
                if cleanup_failure is None:
                    cleanup_failure = exc
            with self._lock:
                self._stopped_at = self._clock()
                if failure is not None:
                    self._record_failure(*failure)
                elif cleanup_failure is not None:
                    self._record_failure(
                        PipelineFailureCategory.SHUTDOWN,
                        "Counting pipeline resources could not close cleanly.",
                    )
                else:
                    self._pipeline_status = CountingPipelineStatus.STOPPED
                    self._camera_status = CameraStatus.ENDED if ended else CameraStatus.CLOSED
                    self._source_exhausted = ended

    def _open_source(self, source: CameraSource) -> bool:
        try:
            source.open()
            return True
        except StreamOpenError:
            if not self._can_recover(source):
                raise
        while self._can_recover(source):
            if self._stop_requested.wait(self._recovery_configuration.retry_delay_seconds):
                return False
            with self._lock:
                self._recovery_attempts += 1
                self._camera_status = CameraStatus.OPENING
            try:
                source.open()
            except StreamOpenError:
                continue
            with self._lock:
                self._recovery_successes += 1
            return True
        raise StreamOpenError("Configured source exhausted bounded open recovery.")

    def _recover_source(
        self,
        source: CameraSource,
        processor: CountingFrameProcessor,
    ) -> bool:
        if not self._can_recover(source):
            return False
        self._preview.clear()
        if source.is_open():
            source.close()
        processor.reset()
        while self._can_recover(source):
            with self._lock:
                self._recovery_attempts += 1
                self._camera_status = CameraStatus.OPENING
            if self._stop_requested.wait(self._recovery_configuration.retry_delay_seconds):
                return False
            try:
                source.open()
            except StreamOpenError:
                continue
            with self._lock:
                self._recovery_successes += 1
                self._camera_status = CameraStatus.RUNNING
            return True
        return False

    def _can_recover(self, source: CameraSource) -> bool:
        configuration = self._configuration
        return (
            self._recovery_configuration.enabled
            and source.is_live
            and configuration is not None
            and configuration.source_type is SourceType.USB
            and self._recovery_attempts < self._recovery_configuration.max_reopen_attempts
            and not self._stop_requested.is_set()
        )

    def _snapshot_locked(self) -> CountingPipelineSnapshot:
        configuration = self._configuration
        binding = self._runtime.active_binding()
        camera = CameraSnapshot(
            source_id=None if configuration is None else configuration.stream_id,
            source_type=None if configuration is None else configuration.source_type,
            display_name=(
                "Not configured" if configuration is None else configuration.identity.display_name
            ),
            status=self._camera_status,
            last_frame_index=self._last_frame_index,
            frames_acquired=self._frames_acquired,
            last_successful_frame_at=self._last_successful_frame_at,
            source_exhausted=self._source_exhausted,
            failure_category=self._failure_category,
            failure_message=self._failure_message,
        )
        return CountingPipelineSnapshot(
            status=self._pipeline_status,
            camera=camera,
            frames_processed=self._frames_processed,
            temporary_processing_failures=self._temporary_processing_failures,
            stale_results_rejected=self._stale_results_rejected,
            active_crossing_lifecycle_id=(
                None if binding is None else binding.crossing_lifecycle_id
            ),
            worker_alive=self._worker_is_alive(),
            failure_category=self._failure_category,
            failure_message=self._failure_message,
            started_at=self._started_at,
            stopped_at=self._stopped_at,
            effective_fps=self._effective_fps(),
            recovery_attempts=self._recovery_attempts,
            recovery_successes=self._recovery_successes,
        )

    def _record_failure(
        self,
        category: PipelineFailureCategory,
        message: str,
    ) -> None:
        self._failure_category = category
        self._failure_message = message
        self._pipeline_status = CountingPipelineStatus.FAILED
        self._camera_status = CameraStatus.FAILED

    def _reset_run_metrics(self) -> None:
        self._frames_acquired = 0
        self._frames_processed = 0
        self._temporary_processing_failures = 0
        self._stale_results_rejected = 0
        self._last_frame_index = None
        self._last_successful_frame_at = None
        self._source_exhausted = False
        self._failure_category = PipelineFailureCategory.NONE
        self._failure_message = None
        self._started_at = None
        self._stopped_at = None
        self._first_frame_monotonic = None
        self._last_frame_monotonic = None
        self._recovery_attempts = 0
        self._recovery_successes = 0

    def _close_configured_source(self) -> None:
        source = self._source
        if source is not None and source.is_open():
            source.close()

    def _worker_is_alive(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _record_frame_timing(self, timestamp: float) -> None:
        self._first_frame_monotonic = (
            timestamp if self._first_frame_monotonic is None else self._first_frame_monotonic
        )
        self._last_frame_monotonic = timestamp

    def _effective_fps(self) -> float:
        if (
            self._frames_acquired < 2
            or self._first_frame_monotonic is None
            or self._last_frame_monotonic is None
        ):
            return 0.0
        duration = self._last_frame_monotonic - self._first_frame_monotonic
        return 0.0 if duration <= 0 else (self._frames_acquired - 1) / duration


def _failure_for(exc: BaseException) -> tuple[PipelineFailureCategory, str]:
    if isinstance(exc, StreamOpenError):
        return (
            PipelineFailureCategory.SOURCE_OPEN,
            "Configured video source could not be opened.",
        )
    if isinstance(exc, StreamFatalReadError):
        return (
            PipelineFailureCategory.SOURCE_READ,
            "Configured video source could not continue reading frames.",
        )
    if isinstance(exc, (DetectorLoadError, DetectionInferenceError)):
        return (
            PipelineFailureCategory.DETECTOR,
            "Detector processing failed for the shared camera pipeline.",
        )
    if isinstance(exc, TrackingError):
        return (
            PipelineFailureCategory.TRACKER,
            "Tracker processing failed for the shared camera pipeline.",
        )
    if isinstance(exc, LiveCrossingError):
        return (
            PipelineFailureCategory.CROSSING,
            "Crossing processing failed for the active counting lifecycle.",
        )
    if isinstance(exc, CameraPipelineLifecycleError):
        return (PipelineFailureCategory.LIFECYCLE, str(exc))
    if isinstance(exc, CameraPipelineProcessingError):
        return (
            PipelineFailureCategory.LIFECYCLE,
            "Camera processing lifecycle could not recover safely.",
        )
    return (
        PipelineFailureCategory.INTERNAL,
        "Shared camera pipeline failed unexpectedly.",
    )


__all__ = ["Clock", "CountingPipelineController"]
