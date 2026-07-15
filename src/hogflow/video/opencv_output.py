"""OpenCV/Supervision annotated-video output for the generic CLI."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType
from typing import Any

from hogflow.core import DependencyUnavailableError, HogFlowError
from hogflow.counting import Line
from hogflow.pipeline import PipelineFrameResult


def _load_runtime() -> tuple[ModuleType, ModuleType, ModuleType]:
    try:
        import cv2
        import numpy as np
        import supervision as sv
    except ImportError as exc:
        raise DependencyUnavailableError(
            "OpenCV, NumPy, and Supervision are required for annotated output. "
            'Install with pip install -e ".[dev]".'
        ) from exc
    return cv2, np, sv


class OpenCVAnnotatedVideoOutput:
    """Render generic tracks, the finite line, and count to one output video.

    Framework arrays and Supervision objects remain private. Calling the object
    with a ``PipelineFrameResult`` writes one frame and returns whether pipeline
    processing should continue; pressing ``q`` in optional display mode returns
    ``False``.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        fps: float,
        width: int,
        height: int,
        line: Line,
        class_name: str,
        show: bool = False,
    ) -> None:
        self.path = Path(path)
        self.line = line
        self.class_name = class_name
        self.show = show
        self._cv2, self._np, self._sv = _load_runtime()
        fourcc_name = "XVID" if self.path.suffix.lower() == ".avi" else "mp4v"
        self._writer: Any = self._cv2.VideoWriter(
            str(self.path),
            self._cv2.VideoWriter_fourcc(*fourcc_name),
            fps,
            (width, height),
        )
        self._closed = False
        if not self._writer.isOpened():
            self._writer.release()
            self._closed = True
            raise HogFlowError(f"OpenCV could not create output video: {self.path}")
        self._box_annotator = self._sv.BoxAnnotator()
        self._label_annotator = self._sv.LabelAnnotator()

    def __call__(self, result: PipelineFrameResult) -> bool:
        """Annotate and write one result, returning ``False`` only on display quit."""

        frame = result.frame
        rgb_frame = self._np.frombuffer(frame.pixels, dtype=self._np.uint8).reshape(
            frame.height,
            frame.width,
            3,
        )
        annotated_frame = self._cv2.cvtColor(rgb_frame, self._cv2.COLOR_RGB2BGR)

        if result.tracks:
            detections = tuple(track.detection for track in result.tracks)
            tracker_ids = self._np.asarray(
                [track.tracker_id for track in result.tracks],
                dtype=int,
            )
            labels = [
                f"{track.detection.class_name} #{track.tracker_id}" for track in result.tracks
            ]
        else:
            detections = result.detections
            tracker_ids = None
            labels = [f"{detection.class_name} (untracked)" for detection in detections]

        if detections:
            xyxy = self._np.asarray(
                [
                    [
                        detection.bounding_box.x_min,
                        detection.bounding_box.y_min,
                        detection.bounding_box.x_max,
                        detection.bounding_box.y_max,
                    ]
                    for detection in detections
                ],
                dtype=float,
            )
            framework_detections = self._sv.Detections(
                xyxy=xyxy,
                confidence=self._np.asarray(
                    [detection.confidence for detection in detections],
                    dtype=float,
                ),
                class_id=self._np.asarray(
                    [detection.class_id for detection in detections],
                    dtype=int,
                ),
                tracker_id=tracker_ids,
            )
            annotated_frame = self._box_annotator.annotate(
                scene=annotated_frame,
                detections=framework_detections,
            )
            annotated_frame = self._label_annotator.annotate(
                scene=annotated_frame,
                detections=framework_detections,
                labels=labels,
            )

        line_start = (round(self.line.start.x), round(self.line.start.y))
        line_end = (round(self.line.end.x), round(self.line.end.y))
        self._cv2.line(annotated_frame, line_start, line_end, (0, 255, 255), 3)
        self._cv2.putText(
            annotated_frame,
            f"COUNT: {result.current_count}",
            (20, 40),
            self._cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 0),
            2,
            self._cv2.LINE_AA,
        )
        self._cv2.putText(
            annotated_frame,
            f"CLASS: {self.class_name}",
            (20, 75),
            self._cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            self._cv2.LINE_AA,
        )
        self._writer.write(annotated_frame)

        if self.show:
            self._cv2.imshow("HogFlow Phase 1 Generic Counter", annotated_frame)
            if self._cv2.waitKey(1) & 0xFF == ord("q"):
                return False
        return True

    def close(self) -> None:
        """Release output resources; repeated calls are safe."""

        if self._closed:
            return
        self._writer.release()
        if self.show:
            self._cv2.destroyAllWindows()
        self._closed = True
