"""Supervision 0.29 ByteTrack adapter for live HogFlow detections."""

from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from math import isfinite
from re import fullmatch
from time import monotonic
from typing import Any, Callable

from hogflow.core import DependencyUnavailableError, InputDataError
from hogflow.models import BoundingBox, Detection, Track
from hogflow.tracking.config import (
    ByteTrackConfiguration,
    byte_track_configuration_fingerprint,
)
from hogflow.tracking.errors import (
    MalformedTrackerOutputError,
    StaleTrackingRequestError,
    TrackerCloseError,
    TrackerInitializationError,
    TrackerLifecycleError,
    TrackerResetError,
)
from hogflow.tracking.models import (
    TrackedObject,
    TrackerMetadata,
    TrackingRequest,
    TrackingResult,
    TrackState,
)


def _load_runtime() -> tuple[Any, Any, Any, str]:
    try:
        import numpy as np
        from supervision import Detections
        from supervision.tracker.byte_tracker.core import ByteTrack
    except ImportError as exc:
        raise DependencyUnavailableError(
            "Supervision, NumPy, and LAP are required for the ByteTrack adapter."
        ) from exc
    except Exception as exc:
        raise DependencyUnavailableError(
            "The local Supervision tracking runtime could not initialize safely."
        ) from exc
    try:
        framework_version = version("supervision")
    except PackageNotFoundError:
        framework_version = "unknown"
    return np, Detections, ByteTrack, framework_version


class SupervisionByteTrackAdapter:
    """Associate detections with temporary IDs using Supervision ByteTrack.

    One adapter instance is bound to one stream lifecycle. Supervision and
    NumPy objects remain private. Returned objects describe only detections
    associated with the current update; lost and removed framework tracks are
    not exposed as currently visible objects.
    """

    def __init__(
        self,
        configuration: ByteTrackConfiguration | None = None,
        *,
        monotonic_clock: Callable[[], float] = monotonic,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._configuration = configuration or ByteTrackConfiguration()
        if not isinstance(self._configuration, ByteTrackConfiguration):
            raise InputDataError("ByteTrack adapter requires ByteTrackConfiguration.")
        self._monotonic = monotonic_clock
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._np: Any | None = None
        self._detections_type: Any | None = None
        self._backend: Any | None = None
        self._metadata: TrackerMetadata | None = None
        self._stream_id: str | None = None
        self._last_sequence: int | None = None

    @property
    def metadata(self) -> TrackerMetadata:
        if self._metadata is None:
            raise TrackerLifecycleError("Tracker metadata is available only after startup.")
        return self._metadata

    @property
    def is_started(self) -> bool:
        return self._backend is not None

    def start(self, stream_id: str) -> None:
        """Initialize ByteTrack and bind it to one opaque stream ID."""

        if (
            not isinstance(stream_id, str)
            or fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", stream_id) is None
        ):
            raise InputDataError("Tracker stream ID must be opaque text.")
        if self.is_started:
            if stream_id != self._stream_id:
                raise TrackerLifecycleError("One ByteTrack instance cannot mix source streams.")
            return
        np, detections_type, backend_type, framework_version = _load_runtime()
        settings = self._configuration
        try:
            backend = backend_type(
                track_activation_threshold=settings.track_activation_threshold,
                lost_track_buffer=settings.lost_track_buffer,
                minimum_matching_threshold=settings.minimum_matching_threshold,
                frame_rate=settings.frame_rate,
                minimum_consecutive_frames=settings.minimum_consecutive_frames,
            )
        except Exception as exc:
            raise TrackerInitializationError(
                "Supervision ByteTrack could not initialize from the validated configuration."
            ) from exc
        fingerprint = byte_track_configuration_fingerprint(settings)
        self._np = np
        self._detections_type = detections_type
        self._backend = backend
        self._metadata = TrackerMetadata(
            tracker_id=f"supervision-bytetrack-{fingerprint[:16]}",
            framework="supervision-bytetrack",
            framework_version=framework_version,
            configuration_fingerprint=fingerprint,
        )
        self._stream_id = stream_id
        self._last_sequence = None

    def update(self, request: TrackingRequest) -> TrackingResult:
        """Convert one request, update ByteTrack, and return HogFlow objects."""

        self._validate_request(request)
        if self._np is None or self._detections_type is None or self._backend is None:
            raise TrackerLifecycleError("Tracker runtime is unavailable after startup.")
        started_monotonic = float(self._monotonic())
        started_at = self._wall_clock()
        private_detections = self._to_framework_detections(request)
        try:
            tracked = self._backend.update_with_detections(private_detections)
        except Exception as exc:
            raise TrackerLifecycleError("Supervision ByteTrack update failed.") from exc
        tracked_objects = self._from_framework_detections(tracked, request)
        completed_monotonic = float(self._monotonic())
        completed_at = self._wall_clock()
        self._last_sequence = request.frame_sequence
        return TrackingResult(
            source_id=request.source_id,
            frame_sequence=request.frame_sequence,
            captured_at=request.captured_at,
            frame_width=request.frame_width,
            frame_height=request.frame_height,
            tracked_objects=tracked_objects,
            tracker_id=self.metadata.tracker_id,
            tracker_version=self.metadata.framework_version,
            configuration_fingerprint=self.metadata.configuration_fingerprint,
            processing_started_at=started_at,
            processing_finished_at=completed_at,
            tracking_latency_ms=max(0.0, completed_monotonic - started_monotonic) * 1000,
        )

    def reset(self) -> None:
        """Clear IDs and association state while retaining the stream binding."""

        if self._backend is None:
            raise TrackerLifecycleError("Tracker must be started before reset.")
        try:
            self._backend.reset()
        except Exception as exc:
            raise TrackerResetError("Supervision ByteTrack reset failed.") from exc
        self._last_sequence = None

    def close(self) -> None:
        """Release private tracker state; repeated calls are safe."""

        backend = self._backend
        if backend is None:
            return
        pending: BaseException | None = None
        try:
            backend.reset()
        except Exception as exc:
            pending = TrackerCloseError("Supervision ByteTrack cleanup failed.")
            pending.__cause__ = exc
        finally:
            self._backend = None
            self._np = None
            self._detections_type = None
            self._stream_id = None
            self._last_sequence = None
        if pending is not None:
            raise pending

    def _validate_request(self, request: TrackingRequest) -> None:
        if not self.is_started or self._stream_id is None:
            raise TrackerLifecycleError("Tracker must be started before update.")
        if not isinstance(request, TrackingRequest):
            raise InputDataError("ByteTrack input must be a TrackingRequest.")
        if request.source_id != self._stream_id:
            raise TrackerLifecycleError("One ByteTrack instance cannot mix source streams.")
        if self._last_sequence is not None and request.frame_sequence <= self._last_sequence:
            raise StaleTrackingRequestError("Tracking requests must have increasing frame IDs.")

    def _to_framework_detections(self, request: TrackingRequest) -> Any:
        np = self._np
        detections_type = self._detections_type
        xyxy = np.asarray(
            [
                (
                    item.bounding_box.x_min,
                    item.bounding_box.y_min,
                    item.bounding_box.x_max,
                    item.bounding_box.y_max,
                )
                for item in request.detections
            ],
            dtype=np.float32,
        ).reshape((-1, 4))
        confidence = np.asarray([item.confidence for item in request.detections], dtype=np.float32)
        class_id = np.asarray([item.class_id for item in request.detections], dtype=int)
        source_index = np.arange(len(request.detections), dtype=int)
        try:
            return detections_type(
                xyxy=xyxy,
                confidence=confidence,
                class_id=class_id,
                data={"hogflow_source_detection_index": source_index},
            )
        except Exception as exc:
            raise MalformedTrackerOutputError(
                "HogFlow detections could not be converted for Supervision ByteTrack."
            ) from exc

    def _from_framework_detections(
        self,
        tracked: Any,
        request: TrackingRequest,
    ) -> tuple[TrackedObject, ...]:
        try:
            length = len(tracked)
        except Exception as exc:
            raise MalformedTrackerOutputError(
                "Supervision ByteTrack returned an invalid result collection."
            ) from exc
        if length == 0:
            return ()
        tracker_ids = getattr(tracked, "tracker_id", None)
        confidence = getattr(tracked, "confidence", None)
        class_ids = getattr(tracked, "class_id", None)
        coordinates = getattr(tracked, "xyxy", None)
        if any(value is None for value in (tracker_ids, confidence, class_ids, coordinates)):
            raise MalformedTrackerOutputError("ByteTrack result omitted required tracking fields.")
        data = getattr(tracked, "data", {})
        source_indices = (
            data.get("hogflow_source_detection_index") if isinstance(data, dict) else None
        )
        if not all(
            len(value) == length for value in (tracker_ids, confidence, class_ids, coordinates)
        ):
            raise MalformedTrackerOutputError("ByteTrack result fields have inconsistent lengths.")
        if source_indices is not None and len(source_indices) != length:
            raise MalformedTrackerOutputError("ByteTrack source references are inconsistent.")

        class_names = {item.class_id: item.class_name for item in request.detections}
        objects: list[TrackedObject] = []
        for index in range(length):
            try:
                raw_track_id = float(tracker_ids[index])
                raw_class_id = float(class_ids[index])
                resolved_confidence = float(confidence[index])
                row = tuple(float(value) for value in coordinates[index])
            except (TypeError, ValueError, OverflowError) as exc:
                raise MalformedTrackerOutputError(
                    "ByteTrack result contains malformed numeric values."
                ) from exc
            if (
                len(row) != 4
                or not raw_track_id.is_integer()
                or not raw_class_id.is_integer()
                or raw_track_id < 0
                or raw_class_id < 0
                or not isfinite(raw_track_id)
                or not isfinite(raw_class_id)
                or not isfinite(resolved_confidence)
                or not all(isfinite(value) for value in row)
                or not 0.0 <= resolved_confidence <= 1.0
            ):
                raise MalformedTrackerOutputError("ByteTrack result contains invalid values.")
            resolved_class_id = int(raw_class_id)
            if resolved_class_id not in class_names:
                raise MalformedTrackerOutputError(
                    "ByteTrack result class is absent from the submitted detections."
                )
            x_min, y_min, x_max, y_max = row
            x_min = min(max(x_min, 0.0), float(request.frame_width))
            y_min = min(max(y_min, 0.0), float(request.frame_height))
            x_max = min(max(x_max, 0.0), float(request.frame_width))
            y_max = min(max(y_max, 0.0), float(request.frame_height))
            if x_min >= x_max or y_min >= y_max:
                raise MalformedTrackerOutputError(
                    "ByteTrack result becomes zero-area after frame clipping."
                )
            source_index: int | None = None
            if source_indices is not None:
                raw_source_index = float(source_indices[index])
                if not isfinite(raw_source_index) or not raw_source_index.is_integer():
                    raise MalformedTrackerOutputError(
                        "ByteTrack result contains an invalid source detection reference."
                    )
                source_index = int(raw_source_index)
                if not 0 <= source_index < len(request.detections):
                    raise MalformedTrackerOutputError(
                        "ByteTrack source detection reference is out of range."
                    )
            detection = Detection(
                BoundingBox(x_min, y_min, x_max, y_max),
                resolved_confidence,
                resolved_class_id,
                class_names[resolved_class_id],
            )
            objects.append(
                TrackedObject(
                    track=Track(int(raw_track_id), detection),
                    source_detection_index=source_index,
                    state=TrackState.VISIBLE,
                )
            )
        return tuple(objects)


__all__ = ["SupervisionByteTrackAdapter"]
