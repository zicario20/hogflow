"""Optional local-only OpenCV preview for live detector results."""

from __future__ import annotations

from types import ModuleType
from typing import Any

from hogflow.core import DependencyUnavailableError
from hogflow.detection.errors import DetectionPreviewError
from hogflow.detection.inference import FrameDetections, LiveDetectionStats, PreviewAction
from hogflow.streaming.models import FramePacket


def _load_preview_runtime() -> tuple[ModuleType, ModuleType]:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise DependencyUnavailableError(
            "OpenCV and NumPy are required only when local preview is enabled."
        ) from exc
    return cv2, np


class OpenCVDetectionPreview:
    """Render ephemeral local frames without recording or persistence."""

    def __init__(
        self,
        window_name: str = "HogFlow live detection",
        *,
        cv2_module: ModuleType | Any | None = None,
        numpy_module: ModuleType | Any | None = None,
    ) -> None:
        if not isinstance(window_name, str) or not window_name.strip():
            raise DetectionPreviewError("Preview window name must be non-empty text.")
        if cv2_module is None or numpy_module is None:
            cv2_module, numpy_module = _load_preview_runtime()
        self._cv2 = cv2_module
        self._np = numpy_module
        self._window_name = window_name.strip()
        self._open = False

    def show(
        self,
        frame: FramePacket,
        detections: FrameDetections,
        statistics: LiveDetectionStats,
    ) -> PreviewAction:
        """Render one current frame and return a local operator action."""

        try:
            rgb = self._np.frombuffer(frame.payload.data, dtype=self._np.uint8).reshape(
                frame.dimensions.height,
                frame.dimensions.width,
                frame.dimensions.channels,
            )
            canvas = self._cv2.cvtColor(rgb, self._cv2.COLOR_RGB2BGR).copy()
            for detection in detections.detections:
                box = detection.bounding_box
                start = (round(box.x_min), round(box.y_min))
                end = (round(box.x_max), round(box.y_max))
                self._cv2.rectangle(canvas, start, end, (0, 255, 0), 2)
                label = f"{detection.class_name} {detection.confidence:.2f}"
                self._cv2.putText(
                    canvas,
                    label,
                    (start[0], max(15, start[1] - 5)),
                    self._cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1,
                    self._cv2.LINE_AA,
                )
            camera_fps = (
                "unknown" if statistics.camera_fps is None else f"{statistics.camera_fps:.1f}"
            )
            age = (
                "unknown"
                if statistics.latest_frame_age_ms is None
                else f"{statistics.latest_frame_age_ms:.1f}ms"
            )
            lines = (
                f"sequence={frame.sequence_number} detections={len(detections.detections)}",
                f"camera_fps={camera_fps} inference_fps={statistics.effective_inference_fps:.1f}",
                f"latency={detections.inference_duration_ms:.1f}ms frame_age={age}",
            )
            for index, line in enumerate(lines):
                self._cv2.putText(
                    canvas,
                    line,
                    (10, 25 + index * 22),
                    self._cv2.FONT_HERSHEY_SIMPLEX,
                    0.55,
                    (255, 255, 255),
                    1,
                    self._cv2.LINE_AA,
                )
            self._cv2.imshow(self._window_name, canvas)
            self._open = True
            key = int(self._cv2.waitKey(1)) & 0xFF
        except Exception:
            raise DetectionPreviewError("Local OpenCV preview failed.") from None
        return PreviewAction.STOP if key in {27, ord("q"), ord("Q")} else PreviewAction.CONTINUE

    def close(self) -> None:
        """Destroy only this preview window; repeated calls are safe."""

        if not self._open:
            return
        self._open = False
        try:
            self._cv2.destroyWindow(self._window_name)
        except Exception:
            raise DetectionPreviewError("Local OpenCV preview cleanup failed.") from None


__all__ = ["OpenCVDetectionPreview"]
