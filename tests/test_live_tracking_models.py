from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest
from _phase5_3_helpers import TIMESTAMP, pig_detection, tracking_request

from hogflow.core import ConfigurationError, InputDataError
from hogflow.models import Track
from hogflow.tracking import (
    ByteTrackConfiguration,
    LiveTrackingStats,
    TrackedObject,
    TrackerMetadata,
    TrackingErrorCategory,
    TrackingHealthState,
    TrackingResult,
    TrackState,
    byte_track_configuration_fingerprint,
)


def test_tracking_request_is_immutable_and_preserves_frame_identity() -> None:
    detection = pig_detection()
    request = tracking_request(7, (detection,))

    assert request.source_id == "camera"
    assert request.frame_sequence == 7
    assert request.detections == (detection,)
    with pytest.raises(FrozenInstanceError):
        request.frame_sequence = 8  # type: ignore[misc]


def test_tracking_request_rejects_out_of_frame_detection() -> None:
    with pytest.raises(InputDataError, match="source frame"):
        tracking_request(0, (pig_detection(x_max=30),))


def test_tracked_object_reuses_canonical_track_and_validates_optional_metadata() -> None:
    tracked = TrackedObject(
        Track(4, pig_detection()),
        source_detection_index=0,
        state=TrackState.VISIBLE,
        age_frames=3,
        hits=2,
        missed_frames=0,
    )

    assert tracked.track.tracker_id == 4
    with pytest.raises(InputDataError):
        TrackedObject(Track(4, pig_detection()), hits=-1)


def test_tracking_result_rejects_non_finite_latency_and_bad_time_order() -> None:
    metadata = TrackerMetadata("tracker", "synthetic", "1", "a" * 64)
    request = tracking_request(1)
    with pytest.raises(InputDataError, match="latency"):
        TrackingResult(
            request.source_id,
            request.frame_sequence,
            request.captured_at,
            request.frame_width,
            request.frame_height,
            (),
            metadata.tracker_id,
            metadata.framework_version,
            metadata.configuration_fingerprint,
            TIMESTAMP,
            TIMESTAMP,
            float("nan"),
        )
    with pytest.raises(InputDataError, match="precede"):
        TrackingResult(
            request.source_id,
            request.frame_sequence,
            request.captured_at,
            request.frame_width,
            request.frame_height,
            (),
            metadata.tracker_id,
            metadata.framework_version,
            metadata.configuration_fingerprint,
            TIMESTAMP,
            datetime(2026, 7, 18, tzinfo=TIMESTAMP.tzinfo),
            0,
        )


@pytest.mark.parametrize(
    "settings",
    (
        {"track_activation_threshold": float("nan")},
        {"minimum_matching_threshold": float("inf")},
        {"lost_track_buffer": -1},
        {"frame_rate": 0},
        {"minimum_consecutive_frames": 0},
    ),
)
def test_bytetrack_configuration_rejects_invalid_values(settings: dict[str, object]) -> None:
    with pytest.raises(ConfigurationError):
        ByteTrackConfiguration(**settings)  # type: ignore[arg-type]


def test_bytetrack_configuration_fingerprint_is_stable_and_sensitive() -> None:
    first = byte_track_configuration_fingerprint(ByteTrackConfiguration())
    second = byte_track_configuration_fingerprint(ByteTrackConfiguration())
    changed = byte_track_configuration_fingerprint(ByteTrackConfiguration(frame_rate=15))

    assert first == second
    assert first != changed
    assert len(first) == 64


def test_tracking_statistics_do_not_misrepresent_stage_accounting() -> None:
    with pytest.raises(InputDataError, match="requests"):
        LiveTrackingStats(
            tracking_requests=2,
            tracking_successes=1,
            tracking_failures=0,
            lifecycle_failures=0,
            zero_detection_updates=0,
            tracks_emitted=1,
            active_tracks_current=1,
            active_tracks_peak=1,
            frames_with_tracks=1,
            frames_without_tracks=0,
            tracker_resets=0,
            tracker_restarts=0,
            tracker_closes=0,
            stale_requests_rejected=0,
            malformed_detections_rejected=0,
            preview_failures=0,
            total_tracking_latency_ms=1,
            last_tracking_latency_ms=1,
            average_tracking_latency_ms=1,
            maximum_tracking_latency_ms=1,
            last_tracking_frame_id=1,
            last_tracking_error=TrackingErrorCategory.NONE,
            current_health_state=TrackingHealthState.RUNNING,
        )


def test_tracker_metadata_rejects_path_like_identity() -> None:
    with pytest.raises(InputDataError):
        TrackerMetadata("C:\\private\\tracker", "synthetic", "1", "a" * 64)
