from __future__ import annotations

from datetime import datetime, timezone

from hogflow.detection.inference import FrameDetections
from hogflow.models import BoundingBox, Detection
from hogflow.tracking.models import TrackingRequest

TIMESTAMP = datetime(2026, 7, 19, tzinfo=timezone.utc)


def pig_detection(
    x_min: float = 1,
    y_min: float = 1,
    x_max: float = 4,
    y_max: float = 4,
    *,
    confidence: float = 0.9,
    class_id: int = 0,
    class_name: str = "pig",
) -> Detection:
    return Detection(
        BoundingBox(x_min, y_min, x_max, y_max),
        confidence,
        class_id,
        class_name,
    )


def tracking_request(
    sequence: int,
    detections: tuple[Detection, ...] = (),
    *,
    source_id: str = "camera",
    width: int = 20,
    height: int = 12,
) -> TrackingRequest:
    return TrackingRequest(
        source_id=source_id,
        frame_sequence=sequence,
        captured_at=TIMESTAMP,
        frame_width=width,
        frame_height=height,
        detections=detections,
    )


def frame_detections(
    sequence: int,
    detections: tuple[Detection, ...] = (),
    *,
    source_id: str = "camera",
    width: int = 8,
    height: int = 6,
) -> FrameDetections:
    return FrameDetections(
        source_id=source_id,
        frame_sequence=sequence,
        captured_at=TIMESTAMP,
        inference_started_at=TIMESTAMP,
        inference_completed_at=TIMESTAMP,
        frame_width=width,
        frame_height=height,
        detections=detections,
        model_id="synthetic-model",
        model_version="1",
        artifact_fingerprint=None,
        inference_duration_ms=1,
    )
