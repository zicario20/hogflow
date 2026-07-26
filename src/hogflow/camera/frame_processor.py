"""Serial detector, tracker, and crossing composition for one camera worker."""

from __future__ import annotations

from collections.abc import Callable

from hogflow.camera.errors import CameraPipelineProcessingError
from hogflow.camera.ports import PreviewFramePublisher
from hogflow.camera.preview_models import PreviewCrossing, PreviewFrame, PreviewTrack
from hogflow.counting import (
    LiveCrossingConfiguration,
    LiveCrossingDetector,
    LiveCrossingResult,
    representative_point,
)
from hogflow.detection import (
    FrameDetections,
    LiveDetector,
    MalformedDetectorOutputError,
)
from hogflow.streaming import FramePacket
from hogflow.tracking import (
    LiveTracker,
    MalformedTrackerOutputError,
    TrackingRequest,
    TrackingResult,
)

CrossingDetectorFactory = Callable[[str], LiveCrossingDetector]


class DetectorTrackingCrossingProcessor:
    """Reuse public Phase 5 detector/tracker/crossing contracts per frame.

    One worker owns this object. Detection and tracking continue while the
    shared lane is idle, but crossing is activated only for the exact lifecycle
    currently bound to an unloading session. Switching or releasing ownership
    clears crossing side state and temporary tracker identity state.
    """

    def __init__(
        self,
        detector: LiveDetector,
        tracker: LiveTracker,
        crossing_detector_factory: CrossingDetectorFactory,
        *,
        preview_publisher: PreviewFramePublisher | None = None,
        preview_configuration: LiveCrossingConfiguration | None = None,
    ) -> None:
        if not callable(crossing_detector_factory):
            raise TypeError("Crossing detector factory must be callable.")
        self._detector = detector
        self._tracker = tracker
        self._crossing_detector_factory = crossing_detector_factory
        if (preview_publisher is None) != (preview_configuration is None):
            raise TypeError(
                "Preview publication requires both publisher and crossing configuration."
            )
        if preview_configuration is not None and (
            not isinstance(preview_configuration, LiveCrossingConfiguration)
            or not preview_configuration.enabled
            or preview_configuration.line is None
        ):
            raise TypeError("Preview requires enabled crossing configuration with a line.")
        self._preview_publisher = preview_publisher
        self._preview_configuration = preview_configuration
        self._crossing_detector: LiveCrossingDetector | None = None
        self._active_crossing_lifecycle_id: str | None = None
        self._source_id: str | None = None

    @property
    def is_started(self) -> bool:
        return self._source_id is not None

    def start(self, source_id: str) -> None:
        """Load one detector and start one tracker for the shared source."""

        if self.is_started:
            if source_id != self._source_id:
                raise CameraPipelineProcessingError(
                    "One frame processor cannot mix source lifecycles."
                )
            return
        detector_loaded = False
        try:
            self._detector.load()
            detector_loaded = True
            self._tracker.start(source_id)
        except Exception:
            if self._tracker.is_started:
                self._tracker.close()
            if detector_loaded:
                self._detector.close()
            raise
        self._source_id = source_id

    def process(
        self,
        frame: FramePacket,
        crossing_lifecycle_id: str | None,
    ) -> LiveCrossingResult | None:
        """Process one exact frame and optionally emit current-lifecycle evidence."""

        self._require_frame(frame)
        self._select_crossing_lifecycle(crossing_lifecycle_id)
        detections = self._detector.infer(frame)
        self._validate_detections(frame, detections)
        request = TrackingRequest(
            source_id=detections.source_id,
            frame_sequence=detections.frame_sequence,
            captured_at=detections.captured_at,
            frame_width=detections.frame_width,
            frame_height=detections.frame_height,
            detections=detections.detections,
        )
        tracking = self._tracker.update(request)
        self._validate_tracking(request, tracking)
        crossing: LiveCrossingResult | None = None
        detector = self._crossing_detector
        if detector is not None:
            crossing = detector.update(tracking)
            if (
                not isinstance(crossing, LiveCrossingResult)
                or crossing.source_id != tracking.source_id
                or crossing.frame_sequence != tracking.frame_sequence
                or crossing.captured_at != tracking.captured_at
                or crossing.crossing_lifecycle_id != crossing_lifecycle_id
            ):
                raise CameraPipelineProcessingError(
                    "Crossing output does not match the active source frame and lifecycle."
                )
        self._publish_preview(frame, tracking, crossing)
        return crossing

    def reset(self) -> None:
        """Clear reconnect-sensitive tracker and crossing state."""

        if not self.is_started:
            raise CameraPipelineProcessingError(
                "Frame processor must start before reconnect reset."
            )
        detector = self._crossing_detector
        self._crossing_detector = None
        self._active_crossing_lifecycle_id = None
        if detector is not None:
            detector.close()
        self._tracker.reset()

    def close(self) -> None:
        """Close all owned resources; repeated calls are safe."""

        pending: BaseException | None = None
        detector = self._crossing_detector
        self._crossing_detector = None
        self._active_crossing_lifecycle_id = None
        if detector is not None:
            try:
                detector.close()
            except BaseException as exc:
                pending = exc
        if self._tracker.is_started:
            try:
                self._tracker.close()
            except BaseException as exc:
                if pending is None:
                    pending = exc
        if self._detector.is_loaded:
            try:
                self._detector.close()
            except BaseException as exc:
                if pending is None:
                    pending = exc
        self._source_id = None
        if pending is not None:
            raise CameraPipelineProcessingError(
                "Frame processor resources could not close cleanly."
            ) from pending

    def _publish_preview(
        self,
        frame: FramePacket,
        tracking: TrackingResult,
        crossing: LiveCrossingResult | None,
    ) -> None:
        """Publish one optional visual value without changing processing outcome."""

        publisher = self._preview_publisher
        configuration = self._preview_configuration
        if publisher is None or configuration is None or configuration.line is None:
            return
        try:
            observations = (
                {}
                if crossing is None
                else {item.tracker_id: item for item in crossing.observations}
            )
            tracks = []
            for tracked_object in tracking.tracked_objects:
                track = tracked_object.track
                detection = track.detection
                box = detection.bounding_box
                observation = observations.get(track.tracker_id)
                anchor = (
                    observation.point
                    if observation is not None
                    else representative_point(
                        box,
                        tracking.frame_width,
                        tracking.frame_height,
                        configuration.anchor,
                    )
                )
                side = (
                    observation.side
                    if observation is not None
                    else configuration.line.classify(anchor, configuration.epsilon)
                )
                tracks.append(
                    PreviewTrack(
                        tracker_id=track.tracker_id,
                        class_id=detection.class_id,
                        class_name=detection.class_name,
                        confidence=detection.confidence,
                        x_min=box.x_min / tracking.frame_width,
                        y_min=box.y_min / tracking.frame_height,
                        x_max=box.x_max / tracking.frame_width,
                        y_max=box.y_max / tracking.frame_height,
                        anchor=anchor,
                        side=side,
                    )
                )
            publisher.publish(
                PreviewFrame(
                    source_id=frame.stream.stream_id,
                    frame_sequence=frame.sequence_number,
                    captured_at=frame.timestamp.acquired_at,
                    frame_width=frame.dimensions.width,
                    frame_height=frame.dimensions.height,
                    rgb24=frame.payload.data,
                    tracks=tuple(tracks),
                    line=configuration.line,
                    crossings=(
                        ()
                        if crossing is None
                        else tuple(
                            PreviewCrossing(item.tracker_id, item.direction)
                            for item in crossing.events
                        )
                    ),
                )
            )
        except Exception:
            try:
                publisher.record_publication_failure()
            except Exception:
                pass

    def _select_crossing_lifecycle(self, lifecycle_id: str | None) -> None:
        if lifecycle_id == self._active_crossing_lifecycle_id:
            return
        previous = self._crossing_detector
        self._crossing_detector = None
        self._active_crossing_lifecycle_id = None
        if previous is not None:
            previous.close()
        if self._tracker.is_started:
            self._tracker.reset()
        if lifecycle_id is None:
            return
        if self._source_id is None:
            raise CameraPipelineProcessingError("Frame processor must start before crossing.")
        detector = self._crossing_detector_factory(lifecycle_id)
        try:
            detector.start(self._source_id)
            if detector.lifecycle_id != lifecycle_id:
                raise CameraPipelineProcessingError(
                    "Crossing detector lifecycle does not match shared-lane provenance."
                )
        except Exception:
            if detector.is_started:
                detector.close()
            raise
        self._crossing_detector = detector
        self._active_crossing_lifecycle_id = lifecycle_id

    def _require_frame(self, frame: FramePacket) -> None:
        if not self.is_started or self._source_id is None:
            raise CameraPipelineProcessingError("Frame processor must start before processing.")
        if not isinstance(frame, FramePacket) or frame.stream.stream_id != self._source_id:
            raise CameraPipelineProcessingError(
                "Frame processor received an unsupported source frame."
            )

    @staticmethod
    def _validate_detections(frame: FramePacket, result: FrameDetections) -> None:
        if not isinstance(result, FrameDetections) or (
            result.source_id != frame.stream.stream_id
            or result.frame_sequence != frame.sequence_number
            or result.captured_at != frame.timestamp.acquired_at
            or result.frame_width != frame.dimensions.width
            or result.frame_height != frame.dimensions.height
        ):
            raise MalformedDetectorOutputError(
                "Detector result does not identify the exact camera frame."
            )

    @staticmethod
    def _validate_tracking(request: TrackingRequest, result: TrackingResult) -> None:
        if not isinstance(result, TrackingResult) or (
            result.source_id != request.source_id
            or result.frame_sequence != request.frame_sequence
            or result.captured_at != request.captured_at
            or result.frame_width != request.frame_width
            or result.frame_height != request.frame_height
        ):
            raise MalformedTrackerOutputError(
                "Tracker result does not identify the exact detection frame."
            )


__all__ = ["CrossingDetectorFactory", "DetectorTrackingCrossingProcessor"]
