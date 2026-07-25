from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hogflow.counting import (
    LineSide,
    LiveCountingConfiguration,
    LiveCrossingDirection,
    LiveCrossingEvent,
    LiveCrossingResult,
    NormalizedPoint,
)

BASE_TIMESTAMP = datetime(2026, 7, 25, tzinfo=timezone.utc)
CROSSING_FINGERPRINT = "a" * 64
LINE_ID = "line-synthetic"


def counting_configuration(
    *,
    positive_direction: LiveCrossingDirection = (LiveCrossingDirection.NEGATIVE_TO_POSITIVE),
    crossing_fingerprint: str = CROSSING_FINGERPRINT,
    maximum_counted_identities: int = 100,
) -> LiveCountingConfiguration:
    return LiveCountingConfiguration(
        enabled=True,
        positive_direction=positive_direction,
        crossing_configuration_fingerprint=crossing_fingerprint,
        maximum_counted_identities=maximum_counted_identities,
    )


def crossing_event(
    frame_sequence: int,
    tracker_id: int,
    direction: LiveCrossingDirection,
    *,
    source_id: str = "camera",
    lifecycle_id: str = "crossing-lifecycle-1",
    previous_frame_sequence: int | None = None,
    captured_at: datetime | None = None,
    crossing_fingerprint: str = CROSSING_FINGERPRINT,
    line_id: str = LINE_ID,
) -> LiveCrossingEvent:
    timestamp = captured_at or BASE_TIMESTAMP + timedelta(seconds=frame_sequence)
    previous_frame = (
        frame_sequence - 1 if previous_frame_sequence is None else previous_frame_sequence
    )
    if direction is LiveCrossingDirection.NEGATIVE_TO_POSITIVE:
        previous_side = LineSide.NEGATIVE
        current_side = LineSide.POSITIVE
        previous_point = NormalizedPoint(0.5, 0.25)
        current_point = NormalizedPoint(0.5, 0.75)
    else:
        previous_side = LineSide.POSITIVE
        current_side = LineSide.NEGATIVE
        previous_point = NormalizedPoint(0.5, 0.75)
        current_point = NormalizedPoint(0.5, 0.25)
    return LiveCrossingEvent(
        source_id=source_id,
        tracker_lifecycle_id=lifecycle_id,
        tracker_id=tracker_id,
        frame_sequence=frame_sequence,
        previous_frame_sequence=previous_frame,
        captured_at=timestamp,
        direction=direction,
        previous_side=previous_side,
        current_side=current_side,
        previous_point=previous_point,
        representative_point=current_point,
        line_id=line_id,
        configuration_fingerprint=crossing_fingerprint,
    )


def crossing_result(
    frame_sequence: int,
    events: tuple[LiveCrossingEvent, ...] = (),
    *,
    source_id: str = "camera",
    lifecycle_id: str = "crossing-lifecycle-1",
    captured_at: datetime | None = None,
    crossing_fingerprint: str = CROSSING_FINGERPRINT,
    line_id: str = LINE_ID,
) -> LiveCrossingResult:
    timestamp = captured_at or BASE_TIMESTAMP + timedelta(seconds=frame_sequence)
    return LiveCrossingResult(
        source_id=source_id,
        tracker_lifecycle_id=lifecycle_id,
        frame_sequence=frame_sequence,
        captured_at=timestamp,
        observations=(),
        events=events,
        line_id=line_id,
        configuration_fingerprint=crossing_fingerprint,
        processing_started_at=timestamp,
        processing_finished_at=timestamp,
        crossing_latency_ms=0,
    )
