from __future__ import annotations

from datetime import datetime, timezone

from hogflow.models import BoundingBox
from hogflow.tracking import TrackedObject, TrackingResult, synthetic_tracked_object

TIMESTAMP = datetime(2026, 7, 25, tzinfo=timezone.utc)


def tracked_object(
    tracker_id: int,
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
) -> TrackedObject:
    return synthetic_tracked_object(
        tracker_id,
        BoundingBox(x_min, y_min, x_max, y_max),
    )


def tracking_result(
    sequence: int,
    tracked_objects: tuple[TrackedObject, ...] = (),
    *,
    source_id: str = "camera",
    width: int = 100,
    height: int = 100,
) -> TrackingResult:
    return TrackingResult(
        source_id=source_id,
        frame_sequence=sequence,
        captured_at=TIMESTAMP,
        frame_width=width,
        frame_height=height,
        tracked_objects=tracked_objects,
        tracker_id="synthetic-tracker",
        tracker_version="1",
        configuration_fingerprint="a" * 64,
        processing_started_at=TIMESTAMP,
        processing_finished_at=TIMESTAMP,
        tracking_latency_ms=0,
    )


def below(tracker_id: int = 1, *, x_center: float = 50) -> TrackedObject:
    return tracked_object(tracker_id, x_center - 10, 10, x_center + 10, 30)


def on_line(tracker_id: int = 1, *, x_center: float = 50) -> TrackedObject:
    return tracked_object(tracker_id, x_center - 10, 30, x_center + 10, 50)


def above(tracker_id: int = 1, *, x_center: float = 50) -> TrackedObject:
    return tracked_object(tracker_id, x_center - 10, 50, x_center + 10, 70)
