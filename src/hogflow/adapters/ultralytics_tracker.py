"""Ultralytics ByteTrack adapter for externally supplied HogFlow detections."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from hogflow.core import DependencyUnavailableError, HogFlowError, InputDataError, get_logger
from hogflow.models import BoundingBox, Detection, Frame, Track

_LOGGER = get_logger(__name__)
_DEFAULT_TRACKER_CONFIGURATION = "bytetrack.yaml"


def _load_tracker_runtime(configuration: str) -> tuple[Any, Any]:
    """Load and construct the current Ultralytics ByteTrack implementation."""

    try:
        import numpy as np
        from ultralytics.trackers.byte_tracker import BYTETracker
        from ultralytics.utils import YAML, IterableSimpleNamespace
        from ultralytics.utils.checks import check_yaml
    except ImportError as exc:
        raise DependencyUnavailableError(
            "Ultralytics tracking dependencies are unavailable. Install the project "
            "runtime dependencies and the Ultralytics LAP tracking dependency."
        ) from exc

    try:
        tracker_arguments = IterableSimpleNamespace(**YAML.load(check_yaml(configuration)))
        tracker = BYTETracker(tracker_arguments)
    except Exception as exc:
        raise HogFlowError(f"Could not initialize ByteTrack from {configuration!r}: {exc}") from exc
    return np, tracker


class _TrackerDetections:
    """Private results-like collection accepted by the installed ByteTrack API."""

    def __init__(self, np: Any, detections: tuple[Detection, ...]) -> None:
        self._np = np
        self.conf = np.asarray([item.confidence for item in detections], dtype=np.float32)
        self.cls = np.asarray([item.class_id for item in detections], dtype=np.float32)
        xyxy = np.asarray(
            [
                [
                    item.bounding_box.x_min,
                    item.bounding_box.y_min,
                    item.bounding_box.x_max,
                    item.bounding_box.y_max,
                ]
                for item in detections
            ],
            dtype=np.float32,
        ).reshape((-1, 4))
        self.xywh = xyxy.copy()
        if len(self.xywh):
            self.xywh[:, 0] = (xyxy[:, 0] + xyxy[:, 2]) / 2.0
            self.xywh[:, 1] = (xyxy[:, 1] + xyxy[:, 3]) / 2.0
            self.xywh[:, 2] = xyxy[:, 2] - xyxy[:, 0]
            self.xywh[:, 3] = xyxy[:, 3] - xyxy[:, 1]

    def __len__(self) -> int:
        return len(self.conf)

    def __getitem__(self, index: Any) -> _TrackerDetections:
        selected = object.__new__(_TrackerDetections)
        selected._np = self._np
        selected.conf = self.conf[index]
        selected.cls = self.cls[index]
        selected.xywh = self.xywh[index]
        if getattr(selected.conf, "ndim", 0) == 0:
            selected.conf = selected.conf.reshape(1)
            selected.cls = selected.cls.reshape(1)
            selected.xywh = selected.xywh.reshape(1, 4)
        return selected


class UltralyticsTracker:
    """Associate HogFlow detections with stateful Ultralytics ByteTrack IDs.

    Unlike ``YOLO.track()``, this adapter calls the installed ByteTrack API with
    detections already produced by ``Detector.predict``. Detection is therefore
    not repeated or discarded. NumPy arrays and ByteTrack output remain private
    to the adapter.
    """

    def __init__(self, configuration: str = _DEFAULT_TRACKER_CONFIGURATION) -> None:
        self.configuration = configuration
        self._np, self._tracker = _load_tracker_runtime(configuration)
        _LOGGER.debug("Initialized Ultralytics ByteTrack adapter")

    def update(self, frame: Frame, detections: Sequence[Detection]) -> tuple[Track, ...]:
        """Associate one frame's detections and return immutable HogFlow tracks."""

        if not isinstance(frame, Frame):
            raise InputDataError("Tracker input must include a HogFlow Frame.")
        detection_tuple = tuple(detections)
        if not all(isinstance(detection, Detection) for detection in detection_tuple):
            raise InputDataError("Tracker detections must contain only HogFlow Detection objects.")

        private_detections = _TrackerDetections(self._np, detection_tuple)
        try:
            tracked_rows = self._tracker.update(private_detections)
        except Exception as exc:
            raise HogFlowError(f"Tracking failed at frame {frame.frame_index}: {exc}") from exc

        tracks: list[Track] = []
        for row in tracked_rows:
            x_min, y_min, x_max, y_max, tracker_id, score, class_id, source_index = row[:8]
            index = int(source_index)
            class_name = (
                detection_tuple[index].class_name
                if 0 <= index < len(detection_tuple)
                else str(int(class_id))
            )
            tracks.append(
                Track(
                    tracker_id=int(tracker_id),
                    detection=Detection(
                        bounding_box=BoundingBox(
                            float(x_min),
                            float(y_min),
                            float(x_max),
                            float(y_max),
                        ),
                        confidence=float(score),
                        class_id=int(class_id),
                        class_name=class_name,
                    ),
                )
            )
        return tuple(tracks)
