"""OpenCV-backed USB and RTSP camera source adapter."""

from __future__ import annotations

from math import isfinite
from threading import RLock
from time import monotonic
from types import ModuleType
from typing import Any, Callable

from hogflow.core import DependencyUnavailableError, get_logger
from hogflow.streaming.configuration import StreamConfiguration
from hogflow.streaming.errors import StreamFatalReadError, StreamOpenError
from hogflow.streaming.health import StreamHealthMonitor
from hogflow.streaming.models import (
    FrameDimensions,
    FramePayload,
    SourceFrame,
    SourceType,
    StreamErrorCategory,
    StreamHealth,
    StreamHealthState,
    StreamIdentity,
    StreamReadResult,
    StreamReadStatus,
    StreamStatistics,
)

LOGGER = get_logger(__name__)
_CaptureFactory = Callable[[object, int, tuple[int, ...]], Any]


def _load_opencv() -> ModuleType:
    try:
        import cv2
    except ImportError as exc:
        raise DependencyUnavailableError(
            'OpenCV is required for local camera input. Install with pip install -e ".[dev]".'
        ) from exc
    return cv2


class OpenCVCameraSource:
    """Acquire USB or RTSP frames as immutable packed-RGB payloads.

    Requested dimensions and FPS are best-effort only. Health reports expose
    observed values, and no OpenCV or NumPy object crosses this adapter.
    Source locators are accessed only at the runtime boundary and never appear
    in logs, exceptions, health, statistics, or representations.
    """

    def __init__(
        self,
        configuration: StreamConfiguration,
        *,
        capture_factory: _CaptureFactory | None = None,
        cv2_module: ModuleType | Any | None = None,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        if configuration.source_type not in {SourceType.USB, SourceType.RTSP, SourceType.FILE}:
            raise StreamOpenError("OpenCV adapter requires an explicit USB, RTSP, or file source.")
        self._configuration = configuration
        self._capture_factory = capture_factory
        self._cv2 = cv2_module
        self._clock = monotonic_clock
        self._monitor = StreamHealthMonitor(
            configuration.identity,
            monotonic_clock=monotonic_clock,
        )
        self._capture: Any | None = None
        self._open = False
        self._lock = RLock()

    @property
    def configuration(self) -> StreamConfiguration:
        """Return requested non-secret settings and protected locator wrapper."""

        return self._configuration

    @property
    def identity(self) -> StreamIdentity:
        return self._configuration.identity

    @property
    def is_live(self) -> bool:
        return self._configuration.source_type is not SourceType.FILE

    def open(self) -> None:
        """Open the configured device/connection and apply best-effort settings."""

        with self._lock:
            if self._open:
                return
            self._monitor.record_open_attempt()
        cv2 = self._cv2 or _load_opencv()
        self._cv2 = cv2
        capture: Any | None = None
        try:
            source = self._source_argument()
            backend = _backend_code(cv2, self._configuration.backend_preference)
            parameters = _timeout_parameters(cv2, self._configuration)
            if self._capture_factory is not None:
                capture = self._capture_factory(source, backend, parameters)
            elif parameters:
                capture = cv2.VideoCapture(source, backend, list(parameters))
            else:
                capture = cv2.VideoCapture(source, backend)
            if capture is None or not capture.isOpened():
                if capture is not None:
                    capture.release()
                raise StreamOpenError("OpenCV could not open the configured camera source.")
            _apply_requested_settings(cv2, capture, self._configuration)
            dimensions, observed_fps = _observed_settings(cv2, capture)
            self._monitor.record_observed_settings(dimensions, observed_fps)
            if self._configuration.warmup_frames:
                self._monitor.transition(StreamHealthState.WARMING_UP)
                for _ in range(self._configuration.warmup_frames):
                    success, frame = capture.read()
                    if not success or frame is None:
                        raise StreamOpenError("Camera warm-up failed before frame delivery.")
            with self._lock:
                self._capture = capture
                self._open = True
            self._monitor.record_open_success()
            LOGGER.debug("Opened %s", self.identity.display_name)
        except DependencyUnavailableError:
            if capture is not None:
                capture.release()
            with self._lock:
                self._capture = None
                self._open = False
            raise
        except StreamOpenError:
            if capture is not None:
                capture.release()
            with self._lock:
                self._capture = None
                self._open = False
            self._monitor.record_fatal_failure(StreamErrorCategory.OPEN)
            raise
        except Exception:
            if capture is not None:
                capture.release()
            with self._lock:
                self._capture = None
            self._open = False
            self._monitor.record_fatal_failure(StreamErrorCategory.OPEN)
            raise StreamOpenError("Camera source failed during sanitized OpenCV setup.") from None

    def read(self) -> StreamReadResult:
        """Return one frame or a temporary live-source failure result."""

        with self._lock:
            capture = self._capture
            opened = self._open
        if not opened or capture is None:
            return StreamReadResult(StreamReadStatus.STOPPED)
        try:
            success, bgr_frame = capture.read()
        except Exception:
            self._monitor.record_fatal_failure(StreamErrorCategory.READ)
            self.close()
            raise StreamFatalReadError(
                "OpenCV camera read failed without source details."
            ) from None
        if not success or bgr_frame is None:
            if not self.is_live:
                return StreamReadResult(StreamReadStatus.END_OF_STREAM)
            self._monitor.record_temporary_failure(StreamErrorCategory.READ)
            return StreamReadResult(
                StreamReadStatus.TEMPORARY_UNAVAILABLE,
                retry_after_seconds=self._configuration.temporary_retry_delay_seconds,
            )
        try:
            if bgr_frame.ndim != 3 or bgr_frame.shape[2] != 3:
                raise ValueError("unexpected frame shape")
            height, width = bgr_frame.shape[:2]
            dimensions = FrameDimensions(int(width), int(height), 3)
            rgb_frame = self._cv2.cvtColor(bgr_frame, self._cv2.COLOR_BGR2RGB)
            payload = FramePayload(rgb_frame.tobytes())
            payload.validate_dimensions(dimensions)
            source_seconds = None
            if self._configuration.source_type is SourceType.FILE:
                position_ms = float(capture.get(self._cv2.CAP_PROP_POS_MSEC))
                if isfinite(position_ms) and position_ms >= 0:
                    source_seconds = position_ms / 1000
        except Exception:
            self._monitor.record_fatal_failure(StreamErrorCategory.READ)
            self.close()
            raise StreamFatalReadError("OpenCV returned an invalid camera frame.") from None
        self._monitor.record_frame(dimensions, at_monotonic=float(self._clock()))
        return StreamReadResult(
            StreamReadStatus.FRAME,
            SourceFrame(dimensions, payload, source_timestamp_seconds=source_seconds),
        )

    def close(self) -> None:
        """Release the camera resource; repeated calls are safe."""

        with self._lock:
            capture = self._capture
            self._capture = None
            self._open = False
        if capture is not None:
            capture.release()
        if self._monitor.health().state is not StreamHealthState.FAILED:
            self._monitor.transition(StreamHealthState.STOPPED)

    def is_open(self) -> bool:
        with self._lock:
            return self._open

    def health(self) -> StreamHealth:
        return self._monitor.health()

    def statistics(self) -> StreamStatistics:
        return self._monitor.statistics()

    def _source_argument(self) -> int | str:
        if self._configuration.source_type is SourceType.USB:
            if self._configuration.device_index is None:
                raise StreamOpenError("USB camera device index is missing.")
            return self._configuration.device_index
        protected = self._configuration.protected_source
        if protected is None:
            raise StreamOpenError("Protected camera or development source is missing.")
        return protected.reveal_for_adapter()

    def __enter__(self) -> OpenCVCameraSource:
        self.open()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()


def _backend_code(cv2: Any, name: str) -> int:
    constants = {
        "any": "CAP_ANY",
        "dshow": "CAP_DSHOW",
        "ffmpeg": "CAP_FFMPEG",
        "gstreamer": "CAP_GSTREAMER",
        "msmf": "CAP_MSMF",
        "v4l2": "CAP_V4L2",
    }
    return int(getattr(cv2, constants[name], getattr(cv2, "CAP_ANY", 0)))


def _timeout_parameters(cv2: Any, configuration: StreamConfiguration) -> tuple[int, ...]:
    if (
        configuration.source_type is not SourceType.RTSP
        or configuration.read_timeout_seconds is None
    ):
        return ()
    milliseconds = max(1, int(configuration.read_timeout_seconds * 1000))
    parameters: list[int] = []
    for constant_name in ("CAP_PROP_OPEN_TIMEOUT_MSEC", "CAP_PROP_READ_TIMEOUT_MSEC"):
        constant = getattr(cv2, constant_name, None)
        if constant is not None:
            parameters.extend((int(constant), milliseconds))
    return tuple(parameters)


def _apply_requested_settings(cv2: Any, capture: Any, configuration: StreamConfiguration) -> None:
    settings = (
        ("CAP_PROP_FRAME_WIDTH", configuration.requested_width),
        ("CAP_PROP_FRAME_HEIGHT", configuration.requested_height),
        ("CAP_PROP_FPS", configuration.requested_fps),
    )
    for constant_name, value in settings:
        if value is not None and hasattr(cv2, constant_name):
            capture.set(getattr(cv2, constant_name), float(value))


def _observed_settings(cv2: Any, capture: Any) -> tuple[FrameDimensions | None, float | None]:
    width = int(capture.get(getattr(cv2, "CAP_PROP_FRAME_WIDTH")))
    height = int(capture.get(getattr(cv2, "CAP_PROP_FRAME_HEIGHT")))
    fps = float(capture.get(getattr(cv2, "CAP_PROP_FPS")))
    dimensions = FrameDimensions(width, height, 3) if width > 0 and height > 0 else None
    observed_fps = fps if isfinite(fps) and fps > 0 else None
    return dimensions, observed_fps


__all__ = ["OpenCVCameraSource"]
