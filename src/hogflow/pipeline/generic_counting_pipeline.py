"""Synchronous orchestration for generic detection, tracking, and counting."""

from __future__ import annotations

from collections.abc import Callable

from hogflow.counting import CrossingEvent, DirectionalLineCounter, Point
from hogflow.detection import Detector
from hogflow.models import Frame, Track
from hogflow.pipeline.models import PipelineFrameResult, PipelineRunSummary
from hogflow.tracking import Tracker
from hogflow.video import VideoSource

FrameResultCallback = Callable[[PipelineFrameResult], bool | None]
CrossingEventCallback = Callable[[CrossingEvent, Frame, int], None]


def _bottom_center(track: Track) -> Point:
    box = track.detection.bounding_box
    return Point(x=(box.x_min + box.x_max) / 2.0, y=box.y_max)


class GenericCountingPipeline:
    """Coordinate approved contracts while delegating all count rules to the counter.

    Execution is synchronous and one frame is retained at a time. The pipeline
    owns the supplied video-source lifetime and closes it on success or failure.
    Output and event callbacks receive only HogFlow models.
    """

    def __init__(
        self,
        source: VideoSource,
        detector: Detector,
        tracker: Tracker,
        counter: DirectionalLineCounter,
        *,
        tracker_state_ttl_frames: int = 300,
    ) -> None:
        if tracker_state_ttl_frames < 0:
            raise ValueError("Tracker-state TTL must be non-negative.")
        self.source = source
        self.detector = detector
        self.tracker = tracker
        self.counter = counter
        self.tracker_state_ttl_frames = tracker_state_ttl_frames

    def run(
        self,
        *,
        max_frames: int | None = None,
        on_frame: FrameResultCallback | None = None,
        on_event: CrossingEventCallback | None = None,
    ) -> PipelineRunSummary:
        """Process frames until source end, callback stop, failure, or ``max_frames``."""

        if max_frames is not None and max_frames <= 0:
            raise ValueError("max_frames must be a positive integer when provided.")

        processed_frames = 0
        crossing_event_count = 0
        last_seen_frame: dict[int, int] = {}
        try:
            while max_frames is None or processed_frames < max_frames:
                frame = self.source.read()
                if frame is None:
                    break

                detections = tuple(self.detector.predict(frame))
                tracks = tuple(self.tracker.update(frame, detections))
                events: list[CrossingEvent] = []
                for track in tracks:
                    last_seen_frame[track.tracker_id] = frame.frame_index
                    event = self.counter.update(track.tracker_id, _bottom_center(track))
                    if event is None:
                        continue
                    events.append(event)
                    crossing_event_count += 1
                    if on_event is not None:
                        on_event(event, frame, self.counter.count)

                self._forget_inactive_trackers(last_seen_frame, frame.frame_index)
                result = PipelineFrameResult(
                    frame=frame,
                    detections=detections,
                    tracks=tracks,
                    crossing_events=tuple(events),
                    current_count=self.counter.count,
                )
                processed_frames += 1
                if on_frame is not None and on_frame(result) is False:
                    break
        finally:
            self.source.close()

        return PipelineRunSummary(
            processed_frames=processed_frames,
            crossing_event_count=crossing_event_count,
            positive_count=self.counter.count,
        )

    def _forget_inactive_trackers(
        self,
        last_seen_frame: dict[int, int],
        frame_index: int,
    ) -> None:
        stale_ids = [
            tracker_id
            for tracker_id, last_seen in last_seen_frame.items()
            if frame_index - last_seen > self.tracker_state_ttl_frames
        ]
        for tracker_id in stale_ids:
            self.counter.forget_tracker(tracker_id)
            del last_seen_frame[tracker_id]
