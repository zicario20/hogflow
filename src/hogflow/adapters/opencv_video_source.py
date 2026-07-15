"""OpenCV-backed implementation of the framework-independent video contract."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any

from hogflow.core import DependencyUnavailableError, InputDataError, get_logger
from hogflow.models import Frame

_LOGGER = get_logger(__name__)


def _load_opencv() -> ModuleType:
    """Load OpenCV only when the concrete adapter is constructed."""

    try:
        import cv2
    except ImportError as exc:
        raise DependencyUnavailableError(
            'OpenCV is required for local video input. Install with pip install -e ".[dev]".'
        ) from exc
    return cv2


class OpenCVVideoSource:
    """Read a local video sequentially as immutable packed-RGB ``Frame`` objects.

    OpenCV-owned BGR arrays remain private to this adapter. Frame indexes begin
    at zero, and timestamps use ``frame_index / fps`` so progression is stable
    even when a container does not expose reliable per-frame timestamps.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.exists():
            raise InputDataError(f"Input video does not exist: {self.path}")
        if not self.path.is_file():
            raise InputDataError(f"Input path is not a file: {self.path}")

        self._cv2 = _load_opencv()
        self._capture: Any = self._cv2.VideoCapture(str(self.path))
        self._closed = False
        if not self._capture.isOpened():
            self._capture.release()
            self._closed = True
            raise InputDataError(f"OpenCV could not open input video: {self.path}")

        self.fps = float(self._capture.get(self._cv2.CAP_PROP_FPS))
        self.width = int(self._capture.get(self._cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._capture.get(self._cv2.CAP_PROP_FRAME_HEIGHT))
        if self.fps <= 0 or self.width <= 0 or self.height <= 0:
            self.close()
            raise InputDataError("Input video has invalid FPS or frame dimensions.")

        self._next_frame_index = 0
        _LOGGER.debug(
            "Opened local video source with fps=%s and dimensions=%sx%s",
            self.fps,
            self.width,
            self.height,
        )

    def read(self) -> Frame | None:
        """Return the next RGB frame, or ``None`` at normal end of input."""

        if self._closed:
            return None

        success, bgr_frame = self._capture.read()
        if not success:
            return None

        if bgr_frame is None or bgr_frame.ndim != 3 or bgr_frame.shape[2] != 3:
            raise InputDataError(
                f"OpenCV returned an invalid color frame at index {self._next_frame_index}."
            )

        height, width = bgr_frame.shape[:2]
        if width != self.width or height != self.height:
            raise InputDataError("Input video changed frame dimensions during sequential decoding.")

        rgb_frame = self._cv2.cvtColor(bgr_frame, self._cv2.COLOR_BGR2RGB)
        frame_index = self._next_frame_index
        self._next_frame_index += 1
        return Frame(
            frame_index=frame_index,
            width=width,
            height=height,
            pixels=rgb_frame.tobytes(),
            timestamp_seconds=frame_index / self.fps,
        )

    def close(self) -> None:
        """Release the capture resource; repeated calls are safe."""

        if self._closed:
            return
        self._capture.release()
        self._closed = True

    def __enter__(self) -> OpenCVVideoSource:
        """Return this open source for context-managed use."""

        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        """Release the capture resource when leaving a context."""

        self.close()
