"""Optional local-only OpenCV preview for live crossing diagnostics."""

from __future__ import annotations

from types import ModuleType
from typing import Any

from hogflow.adapters.opencv_tracking_preview import OpenCVTrackingPreview
from hogflow.counting.live_errors import CrossingPreviewError
from hogflow.counting.live_models import (
    LiveCrossingConfiguration,
    LiveCrossingResult,
    LiveCrossingStats,
)
from hogflow.detection.inference import FrameDetections, LiveDetectionStats, PreviewAction
from hogflow.streaming.models import FramePacket
from hogflow.tracking.models import LiveTrackingStats, TrackingResult


class OpenCVCrossingPreview(OpenCVTrackingPreview):
    """Render current tracks, line geometry, anchors, and crossing events.

    The preview is ephemeral. It does not retain frames, save media, or display
    an accumulated animal count.
    """

    def __init__(
        self,
        configuration: LiveCrossingConfiguration,
        window_name: str = "HogFlow live crossing",
        *,
        show_track_ids: bool = True,
        cv2_module: ModuleType | Any | None = None,
        numpy_module: ModuleType | Any | None = None,
    ) -> None:
        if not isinstance(configuration, LiveCrossingConfiguration) or not configuration.enabled:
            raise CrossingPreviewError("Crossing preview requires enabled configuration.")
        super().__init__(
            window_name,
            show_track_ids=show_track_ids,
            cv2_module=cv2_module,
            numpy_module=numpy_module,
        )
        self._crossing_configuration = configuration

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
        """Render one current frame and optionally request cooperative stop."""

        del detections
        try:
            rgb = self._np.frombuffer(frame.payload.data, dtype=self._np.uint8).reshape(
                frame.dimensions.height,
                frame.dimensions.width,
                frame.dimensions.channels,
            )
            canvas = self._cv2.cvtColor(rgb, self._cv2.COLOR_RGB2BGR).copy()
            configuration = crossing.configuration_fingerprint
            observations = {
                observation.tracker_id: observation for observation in crossing.observations
            }
            line = self._crossing_configuration.line
            if line is None:
                raise CrossingPreviewError("Crossing preview requires a configured line.")
            line_start = self._pixel_point(frame, line.start.x, line.start.y)
            line_end = self._pixel_point(frame, line.end.x, line.end.y)
            self._cv2.line(canvas, line_start, line_end, (255, 255, 0), 2)

            for tracked_object in tracking.tracked_objects:
                track = tracked_object.track
                box = track.detection.bounding_box
                start = (round(box.x_min), round(box.y_min))
                end = (round(box.x_max), round(box.y_max))
                self._cv2.rectangle(canvas, start, end, (0, 200, 255), 2)
                observation = observations.get(track.tracker_id)
                side = "unknown" if observation is None else observation.side.value
                if observation is not None:
                    anchor = self._pixel_point(
                        frame,
                        observation.point.x,
                        observation.point.y,
                    )
                    self._cv2.circle(canvas, anchor, 4, (255, 0, 255), -1)
                identity = f" id={track.tracker_id}" if self._show_track_ids else ""
                label = (
                    f"{track.detection.class_name}{identity} "
                    f"{track.detection.confidence:.2f} side={side}"
                )
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
            event_text = "crossing_event=none"
            if crossing.events:
                latest = crossing.events[-1]
                event_text = (
                    f"crossing_event={latest.direction.value} tracker_id={latest.tracker_id}"
                )
            lines = (
                f"sequence={frame.sequence_number} visible_tracks={len(tracking.tracked_objects)}",
                (f"camera_fps={camera_fps} tracking_latency={tracking.tracking_latency_ms:.1f}ms"),
                (
                    f"crossing_latency={crossing.crossing_latency_ms:.1f}ms "
                    f"crossing_health={crossing_statistics.health_state.value}"
                ),
                event_text,
                f"line_id={crossing.line_id} config={configuration[:8]}",
            )
            for index, text in enumerate(lines):
                self._cv2.putText(
                    canvas,
                    text,
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
        except CrossingPreviewError:
            raise
        except Exception:
            raise CrossingPreviewError("Local OpenCV crossing preview failed.") from None
        return PreviewAction.STOP if key in {27, ord("q"), ord("Q")} else PreviewAction.CONTINUE

    @staticmethod
    def _pixel_point(frame: FramePacket, x: float, y: float) -> tuple[int, int]:
        return (
            round(x * (frame.dimensions.width - 1)),
            round(y * (frame.dimensions.height - 1)),
        )

    def close(self) -> None:
        """Destroy the local window and sanitize expected preview failures."""

        try:
            super().close()
        except Exception:
            raise CrossingPreviewError("Local OpenCV crossing preview cleanup failed.") from None


__all__ = ["OpenCVCrossingPreview"]
