from __future__ import annotations

from datetime import datetime, timezone

import pytest
from _phase5_4_helpers import tracked_object

from hogflow.camera import CameraPipelineProcessingError, DetectorTrackingCrossingProcessor
from hogflow.counting import (
    LiveCrossingConfiguration,
    LiveCrossingDirection,
    NormalizedLine,
    NormalizedPoint,
    VirtualLineCrossingDetector,
)
from hogflow.detection import EmptyDetector
from hogflow.streaming import (
    FrameDimensions,
    FramePacket,
    FramePayload,
    FrameTimestamp,
    SourceType,
    StreamIdentity,
)
from hogflow.tracking import ScriptedTracker


def packet(sequence: int) -> FramePacket:
    dimensions = FrameDimensions(100, 100, 3)
    return FramePacket(
        stream=StreamIdentity("shared_lane", SourceType.SYNTHETIC, "Synthetic source"),
        sequence_number=sequence,
        timestamp=FrameTimestamp(
            datetime(2026, 7, 26, 12, 0, sequence, tzinfo=timezone.utc),
            float(sequence),
        ),
        dimensions=dimensions,
        payload=FramePayload(bytes(dimensions.width * dimensions.height * 3)),
    )


def processor() -> DetectorTrackingCrossingProcessor:
    tracker = ScriptedTracker(
        {
            0: (tracked_object(7, 60, 20, 80, 60),),
            1: (tracked_object(7, 20, 20, 40, 60),),
        }
    )
    configuration = LiveCrossingConfiguration(
        enabled=True,
        line=NormalizedLine(
            NormalizedPoint(0.5, 0),
            NormalizedPoint(0.5, 1),
        ),
    )
    return DetectorTrackingCrossingProcessor(
        EmptyDetector(),
        tracker,
        lambda lifecycle_id: VirtualLineCrossingDetector(
            configuration,
            lifecycle_id_factory=lambda _generation: lifecycle_id,
        ),
    )


def test_frame_processor_reuses_detector_tracker_and_exact_crossing_lifecycle() -> None:
    value = processor()
    value.start("shared_lane")

    first = value.process(packet(0), "session-crossing-1")
    second = value.process(packet(1), "session-crossing-1")

    assert first is not None and first.events == ()
    assert second is not None
    assert second.crossing_lifecycle_id == "session-crossing-1"
    assert second.events[0].direction is LiveCrossingDirection.NEGATIVE_TO_POSITIVE
    value.close()
    assert not value.is_started


def test_frame_processor_disables_crossing_while_lane_is_idle() -> None:
    value = processor()
    value.start("shared_lane")

    assert value.process(packet(0), None) is None
    assert value.process(packet(1), None) is None
    value.close()


def test_frame_processor_rejects_crossing_factory_lifecycle_mismatch() -> None:
    value = DetectorTrackingCrossingProcessor(
        EmptyDetector(),
        ScriptedTracker({}),
        lambda _lifecycle_id: VirtualLineCrossingDetector(
            LiveCrossingConfiguration(
                enabled=True,
                line=NormalizedLine(
                    NormalizedPoint(0.5, 0),
                    NormalizedPoint(0.5, 1),
                ),
            )
        ),
    )
    value.start("shared_lane")

    with pytest.raises(CameraPipelineProcessingError, match="lifecycle"):
        value.process(packet(0), "externally-assigned")

    value.close()


def test_crossing_detector_default_lifecycle_semantics_remain_backward_compatible() -> None:
    detector = VirtualLineCrossingDetector(
        LiveCrossingConfiguration(
            enabled=True,
            line=NormalizedLine(NormalizedPoint(0, 0.5), NormalizedPoint(1, 0.5)),
        )
    )

    detector.start("shared_lane")
    assert detector.lifecycle_id == "crossing-lifecycle-1"
    detector.reset()
    assert detector.lifecycle_id == "crossing-lifecycle-2"
