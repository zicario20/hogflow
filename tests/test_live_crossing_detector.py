from __future__ import annotations

import pytest
from _phase5_4_helpers import above, below, on_line, tracked_object, tracking_result

from hogflow.core import InputDataError
from hogflow.counting import (
    CrossingLifecycleError,
    LineSide,
    LiveCrossingConfiguration,
    LiveCrossingDirection,
    NormalizedLine,
    NormalizedPoint,
    StaleCrossingRequestError,
    TrackAnchor,
    VirtualLineCrossingDetector,
    representative_point,
)


def _configuration(*, retention: int = 30, anchor: TrackAnchor = TrackAnchor.BOTTOM_CENTER):
    return LiveCrossingConfiguration(
        enabled=True,
        line=NormalizedLine(NormalizedPoint(0.2, 0.5), NormalizedPoint(0.8, 0.5)),
        anchor=anchor,
        epsilon=0.01,
        absent_track_retention_updates=retention,
    )


def _detector(*, retention: int = 30) -> VirtualLineCrossingDetector:
    detector = VirtualLineCrossingDetector(_configuration(retention=retention))
    detector.start("camera")
    return detector


def test_representative_point_supports_bottom_center_and_center() -> None:
    box = tracked_object(1, 20, 10, 60, 50).track.detection.bounding_box

    assert representative_point(box, 100, 100, TrackAnchor.BOTTOM_CENTER) == NormalizedPoint(
        0.4, 0.5
    )
    assert representative_point(box, 100, 100, TrackAnchor.CENTER) == NormalizedPoint(0.4, 0.3)


def test_representative_point_is_independent_from_frame_resolution() -> None:
    small = tracked_object(1, 20, 10, 60, 50).track.detection.bounding_box
    large = tracked_object(1, 40, 20, 120, 100).track.detection.bounding_box

    assert representative_point(small, 100, 100, TrackAnchor.BOTTOM_CENTER) == (
        representative_point(large, 200, 200, TrackAnchor.BOTTOM_CENTER)
    )


def test_first_observation_and_repeated_same_side_emit_no_event() -> None:
    detector = _detector()

    first = detector.update(tracking_result(0, (below(),)))
    second = detector.update(tracking_result(1, (below(),)))

    assert first.events == ()
    assert second.events == ()
    assert second.observations[0].side is LineSide.NEGATIVE


@pytest.mark.parametrize(
    "first,current,direction",
    (
        (below(), above(), LiveCrossingDirection.NEGATIVE_TO_POSITIVE),
        (above(), below(), LiveCrossingDirection.POSITIVE_TO_NEGATIVE),
    ),
)
def test_opposite_stable_sides_emit_directional_event(first, current, direction) -> None:
    detector = _detector()
    detector.update(tracking_result(0, (first,)))

    result = detector.update(tracking_result(1, (current,)))

    assert len(result.events) == 1
    assert result.events[0].direction is direction
    assert result.events[0].tracker_id == 1
    assert result.events[0].previous_frame_sequence == 0


@pytest.mark.parametrize("first,current", ((below(), above()), (above(), below())))
def test_on_line_preserves_last_stable_side(first, current) -> None:
    detector = _detector()
    detector.update(tracking_result(0, (first,)))
    middle = detector.update(tracking_result(1, (on_line(),)))
    result = detector.update(tracking_result(2, (current,)))

    assert middle.events == ()
    assert middle.observations[0].side is LineSide.ON_LINE
    assert len(result.events) == 1
    assert result.events[0].previous_frame_sequence == 0


def test_on_line_as_first_observation_does_not_invent_previous_side() -> None:
    detector = _detector()

    assert detector.update(tracking_result(0, (on_line(),))).events == ()
    assert detector.update(tracking_result(1, (above(),))).events == ()


def test_near_line_oscillation_does_not_repeat_events() -> None:
    detector = _detector()
    detector.update(tracking_result(0, (below(),)))
    for sequence, y_max in enumerate((49.5, 50.2, 49.8), start=1):
        near = tracked_object(1, 40, y_max - 20, 60, y_max)
        assert detector.update(tracking_result(sequence, (near,))).events == ()

    crossing = detector.update(tracking_result(4, (above(),)))
    remaining = detector.update(tracking_result(5, (above(),)))

    assert len(crossing.events) == 1
    assert remaining.events == ()


def test_multiple_tracks_have_independent_state_and_events() -> None:
    detector = _detector()
    detector.update(tracking_result(0, (below(1), above(2))))

    result = detector.update(tracking_result(1, (above(1), below(2))))

    assert [event.tracker_id for event in result.events] == [1, 2]
    assert [event.direction for event in result.events] == [
        LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
        LiveCrossingDirection.POSITIVE_TO_NEGATIVE,
    ]


def test_empty_result_and_disappearance_do_not_emit_event() -> None:
    detector = _detector()
    detector.update(tracking_result(0, (below(),)))

    assert detector.update(tracking_result(1)).events == ()


def test_absent_identity_is_removed_after_configured_update_limit() -> None:
    detector = _detector(retention=1)
    detector.update(tracking_result(0, (below(),)))
    detector.update(tracking_result(1))
    assert detector.statistics().active_identities_current == 1

    detector.update(tracking_result(2))
    assert detector.statistics().active_identities_current == 0
    assert detector.update(tracking_result(3, (above(),))).events == ()


def test_reset_clears_side_state_and_changes_lifecycle_identity() -> None:
    detector = _detector()
    detector.update(tracking_result(0, (below(),)))
    first_lifecycle = detector.lifecycle_id

    detector.reset()
    result = detector.update(tracking_result(0, (above(),)))

    assert result.events == ()
    assert result.tracker_lifecycle_id != first_lifecycle
    assert detector.statistics().resets == 1


def test_mixed_stream_and_update_before_start_are_rejected() -> None:
    not_started = VirtualLineCrossingDetector(_configuration())
    with pytest.raises(CrossingLifecycleError, match="started"):
        not_started.update(tracking_result(0))

    detector = _detector()
    with pytest.raises(CrossingLifecycleError, match="mix"):
        detector.update(tracking_result(0, source_id="camera-b"))


def test_stale_and_repeated_sequences_are_rejected() -> None:
    detector = _detector()
    detector.update(tracking_result(2, (below(),)))

    with pytest.raises(StaleCrossingRequestError, match="increasing"):
        detector.update(tracking_result(2, (above(),)))
    assert detector.statistics().stale_requests_rejected == 1


def test_large_sequence_gap_emits_at_current_observation_without_interpolation() -> None:
    detector = _detector()
    detector.update(tracking_result(2, (below(),)))

    result = detector.update(tracking_result(200, (above(),)))

    assert len(result.events) == 1
    assert result.events[0].previous_frame_sequence == 2
    assert result.events[0].frame_sequence == 200


def test_reversing_line_endpoints_reverses_side_and_event_direction() -> None:
    configuration = LiveCrossingConfiguration(
        enabled=True,
        line=NormalizedLine(NormalizedPoint(0.8, 0.5), NormalizedPoint(0.2, 0.5)),
        epsilon=0.01,
    )
    detector = VirtualLineCrossingDetector(configuration)
    detector.start("camera")
    detector.update(tracking_result(0, (below(),)))

    result = detector.update(tracking_result(1, (above(),)))

    assert result.events[0].direction is LiveCrossingDirection.POSITIVE_TO_NEGATIVE


def test_crossing_outside_finite_segment_is_not_an_event() -> None:
    detector = _detector()
    detector.update(tracking_result(0, (below(x_center=90),)))

    result = detector.update(tracking_result(1, (above(x_center=90),)))

    assert result.events == ()


def test_close_is_idempotent_and_prevents_later_updates() -> None:
    detector = _detector()

    detector.close()
    detector.close()

    assert not detector.is_started
    assert detector.statistics().closes == 1
    with pytest.raises(CrossingLifecycleError):
        detector.update(tracking_result(0))


def test_disabled_configuration_cannot_be_used_as_active_detector() -> None:
    detector = VirtualLineCrossingDetector(LiveCrossingConfiguration())
    detector.start("camera")

    with pytest.raises(CrossingLifecycleError, match="enabled"):
        detector.update(tracking_result(0))


def test_representative_point_rejects_invalid_dimensions() -> None:
    box = below().track.detection.bounding_box

    with pytest.raises(InputDataError):
        representative_point(box, 0, 100, TrackAnchor.BOTTOM_CENTER)
