from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from threading import Thread

import pytest

from hogflow.camera import (
    LatestPreviewFrameChannel,
    PreviewConfiguration,
    PreviewCrossing,
    PreviewFailureCategory,
    PreviewFrame,
    PreviewHealthState,
    PreviewTrack,
)
from hogflow.counting import (
    LineSide,
    LiveCrossingDirection,
    NormalizedLine,
    NormalizedPoint,
)
from hogflow.presentation import PreviewPrimitiveKind, build_preview_render_plan


def preview_frame(sequence: int = 0) -> PreviewFrame:
    return PreviewFrame(
        source_id="shared_lane",
        frame_sequence=sequence,
        captured_at=datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc),
        frame_width=4,
        frame_height=2,
        rgb24=bytes([sequence % 256]) * 24,
        tracks=(
            PreviewTrack(
                tracker_id=42,
                class_id=0,
                class_name="pig",
                confidence=0.9,
                x_min=0.25,
                y_min=0.0,
                x_max=0.75,
                y_max=1.0,
                anchor=NormalizedPoint(0.5, 1.0),
                side=LineSide.POSITIVE,
            ),
        ),
        line=NormalizedLine(NormalizedPoint(0.5, 0.0), NormalizedPoint(0.5, 1.0)),
        crossings=(PreviewCrossing(42, LiveCrossingDirection.NEGATIVE_TO_POSITIVE),),
    )


def test_preview_frame_is_immutable_and_hides_ephemeral_pixels_from_repr() -> None:
    frame = preview_frame()

    assert "rgb24=<ephemeral>" in repr(frame)
    assert "b'\\x00" not in repr(frame)
    with pytest.raises(FrozenInstanceError):
        frame.frame_sequence = 2  # type: ignore[misc]


def test_latest_frame_replaces_previous_without_accumulation() -> None:
    channel = LatestPreviewFrameChannel()

    channel.publish(preview_frame(1))
    channel.publish(preview_frame(2))
    snapshot = channel.snapshot()
    latest = channel.take_latest()

    assert latest is not None and latest.frame_sequence == 2
    assert snapshot.frames_published == 2
    assert snapshot.frames_replaced == 1
    assert snapshot.frame_available
    assert channel.snapshot().frames_consumed == 1
    assert not channel.snapshot().frame_available
    assert channel.retained_latest() is latest
    assert channel.take_latest() is None
    assert not hasattr(channel, "_queue")
    assert not hasattr(channel, "_history")


def test_disabled_preview_never_retains_frames() -> None:
    channel = LatestPreviewFrameChannel(PreviewConfiguration(enabled=False))

    channel.publish(preview_frame())

    assert channel.take_latest() is None
    assert channel.snapshot().health_state is PreviewHealthState.DISABLED
    assert channel.snapshot().frames_published == 0


def test_render_failure_disables_preview_but_not_channel_owner() -> None:
    channel = LatestPreviewFrameChannel()
    channel.publish(preview_frame())

    failed = channel.record_render_failure()
    channel.publish(preview_frame(1))

    assert failed.health_state is PreviewHealthState.FAILED
    assert failed.failure_category is PreviewFailureCategory.RENDERING
    assert channel.take_latest() is None
    assert channel.snapshot().render_failures == 1


def test_publication_failure_is_degraded_and_next_success_recovers() -> None:
    channel = LatestPreviewFrameChannel()

    channel.record_publication_failure()
    assert channel.snapshot().health_state is PreviewHealthState.DEGRADED

    channel.publish(preview_frame())

    assert channel.snapshot().health_state is PreviewHealthState.AVAILABLE
    assert channel.snapshot().publication_failures == 1


def test_preview_fps_uses_bounded_aggregate_timing() -> None:
    times = iter((1.0, 1.5, 2.0))
    channel = LatestPreviewFrameChannel(monotonic_clock=lambda: next(times))

    channel.publish(preview_frame(0))
    channel.publish(preview_frame(1))
    channel.publish(preview_frame(2))

    assert channel.snapshot().effective_preview_fps == pytest.approx(2.0)


def test_preview_channel_is_safe_for_one_publisher_and_one_consumer() -> None:
    channel = LatestPreviewFrameChannel()

    publisher = Thread(
        target=lambda: [channel.publish(preview_frame(index)) for index in range(100)]
    )
    consumer = Thread(target=lambda: [channel.take_latest() for _ in range(100)])
    publisher.start()
    consumer.start()
    publisher.join()
    consumer.join()

    snapshot = channel.snapshot()
    assert snapshot.frames_published == 100
    assert snapshot.frames_consumed <= 100
    assert snapshot.frames_replaced + snapshot.frames_consumed <= 100


def test_overlay_render_plan_contains_line_box_id_anchor_direction_and_dimensions() -> None:
    plan = build_preview_render_plan(
        preview_frame(7),
        diagnostic_lines=("camera=Running", "pipeline=Running"),
        maximum_width=2,
        maximum_height=2,
    )

    kinds = tuple(item.kind for item in plan.primitives)
    text = tuple(item.text for item in plan.primitives if item.kind is PreviewPrimitiveKind.TEXT)
    assert plan.subsample == 2
    assert PreviewPrimitiveKind.LINE in kinds
    assert PreviewPrimitiveKind.RECTANGLE in kinds
    assert PreviewPrimitiveKind.POINT in kinds
    assert any("id=42" in item for item in text)
    assert any("crossing=negative_to_positive" in item for item in text)
    assert any("dimensions=4x2" in item for item in text)
    assert plan.ppm_data.startswith(b"P6\n4 2\n255\n")
