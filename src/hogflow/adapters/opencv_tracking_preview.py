"""Optional local-only OpenCV preview for temporary tracking identities."""

from __future__ import annotations

from types import ModuleType
from typing import Any

from hogflow.adapters.opencv_detection_preview import OpenCVDetectionPreview
from hogflow.detection.errors import DetectionPreviewError
from hogflow.detection.inference import FrameDetections, LiveDetectionStats, PreviewAction
from hogflow.streaming.models import FramePacket
from hogflow.tracking.errors import TrackingPreviewError
from hogflow.tracking.models import LiveTrackingStats, TrackingResult


class OpenCVTrackingPreview(OpenCVDetectionPreview):
    """Render current visible track IDs without recording or counting."""

    def __init__(
        self,
        window_name: str = "HogFlow live tracking",
        *,
        show_track_ids: bool = True,
        cv2_module: ModuleType | Any | None = None,
        numpy_module: ModuleType | Any | None = None,
    ) -> None:
        if not isinstance(show_track_ids, bool):
            raise TrackingPreviewError("show_track_ids must be boolean.")
        super().__init__(
            window_name,
            cv2_module=cv2_module,
            numpy_module=numpy_module,
        )
        self._show_track_ids = show_track_ids

    def show_tracking(
        self,
        frame: FramePacket,
        detections: FrameDetections,
        tracking: TrackingResult,
        detection_statistics: LiveDetectionStats,
        tracking_statistics: LiveTrackingStats,
    ) -> PreviewAction:
        """Render one frame with current temporary IDs and bounded telemetry."""

        del detections
        try:
            rgb = self._np.frombuffer(frame.payload.data, dtype=self._np.uint8).reshape(
                frame.dimensions.height,
                frame.dimensions.width,
                frame.dimensions.channels,
            )
            canvas = self._cv2.cvtColor(rgb, self._cv2.COLOR_RGB2BGR).copy()
            for tracked_object in tracking.tracked_objects:
                track = tracked_object.track
                detection = track.detection
                box = detection.bounding_box
                start = (round(box.x_min), round(box.y_min))
                end = (round(box.x_max), round(box.y_max))
                self._cv2.rectangle(canvas, start, end, (0, 200, 255), 2)
                identity = f" id={track.tracker_id}" if self._show_track_ids else ""
                label = f"{detection.class_name}{identity} {detection.confidence:.2f}"
                self._cv2.putText(
                    canvas,
                    label,
                    (start[0], max(15, start[1] - 5)),
                    self._cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 200, 255),
                    1,
                    self._cv2.LINE_AA,
                )
            camera_fps = (
                "unknown"
                if detection_statistics.camera_fps is None
                else f"{detection_statistics.camera_fps:.1f}"
            )
            lines = (
                f"sequence={frame.sequence_number} visible_tracks={len(tracking.tracked_objects)}",
                (
                    f"camera_fps={camera_fps} "
                    f"inference_fps={detection_statistics.effective_inference_fps:.1f}"
                ),
                (
                    f"tracking_latency={tracking.tracking_latency_ms:.1f}ms "
                    f"tracker_health={tracking_statistics.current_health_state.value}"
                ),
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
            raise TrackingPreviewError("Local OpenCV tracking preview failed.") from None
        return PreviewAction.STOP if key in {27, ord("q"), ord("Q")} else PreviewAction.CONTINUE

    def close(self) -> None:
        """Destroy the tracking window and translate expected preview failures."""

        try:
            super().close()
        except DetectionPreviewError:
            raise TrackingPreviewError("Local OpenCV tracking preview cleanup failed.") from None


__all__ = ["OpenCVTrackingPreview"]
