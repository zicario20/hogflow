import pytest
from _phase5_3_helpers import pig_detection, tracking_request

from hogflow.core import InputDataError
from hogflow.tracking import (
    DeterministicIoUTracker,
    EmptyTracker,
    FailingTracker,
    FatalTrackingError,
    SlowTracker,
    StaleTrackingRequestError,
    TemporaryTrackingError,
    TrackerLifecycleError,
)


def test_one_object_keeps_one_temporary_id_across_frames() -> None:
    tracker = DeterministicIoUTracker(iou_threshold=0.2)
    tracker.start("camera")

    first = tracker.update(tracking_request(0, (pig_detection(1, 1, 5, 5),)))
    second = tracker.update(tracking_request(1, (pig_detection(2, 1, 6, 5),)))

    assert first.tracked_objects[0].track.tracker_id == 0
    assert second.tracked_objects[0].track.tracker_id == 0
    assert second.tracked_objects[0].hits == 2


def test_two_objects_keep_separate_ids() -> None:
    tracker = DeterministicIoUTracker(iou_threshold=0.2)
    tracker.start("camera")
    detections = (pig_detection(1, 1, 4, 4), pig_detection(10, 1, 14, 4))

    first = tracker.update(tracking_request(0, detections))
    second = tracker.update(tracking_request(1, detections))

    assert [item.track.tracker_id for item in first.tracked_objects] == [0, 1]
    assert [item.track.tracker_id for item in second.tracked_objects] == [0, 1]


def test_brief_miss_preserves_identity_within_tolerance() -> None:
    tracker = DeterministicIoUTracker(iou_threshold=0.2, lost_track_buffer=1)
    tracker.start("camera")
    tracker.update(tracking_request(0, (pig_detection(),)))
    assert tracker.update(tracking_request(1)).tracked_objects == ()

    returned = tracker.update(tracking_request(2, (pig_detection(),)))

    assert returned.tracked_objects[0].track.tracker_id == 0


def test_disappearance_beyond_tolerance_creates_new_id() -> None:
    tracker = DeterministicIoUTracker(iou_threshold=0.2, lost_track_buffer=1)
    tracker.start("camera")
    tracker.update(tracking_request(0, (pig_detection(),)))
    tracker.update(tracking_request(1))
    tracker.update(tracking_request(2))

    returned = tracker.update(tracking_request(3, (pig_detection(),)))

    assert returned.tracked_objects[0].track.tracker_id == 1


def test_zero_detections_and_frame_id_gaps_remain_valid() -> None:
    tracker = DeterministicIoUTracker()
    tracker.start("camera")

    result = tracker.update(tracking_request(9))

    assert result.frame_sequence == 9
    assert result.tracked_objects == ()


def test_one_instance_rejects_cross_stream_state_leakage() -> None:
    tracker = EmptyTracker()
    tracker.start("camera-a")

    with pytest.raises(TrackerLifecycleError, match="mix"):
        tracker.update(tracking_request(0, source_id="camera-b"))

    other = EmptyTracker()
    other.start("camera-b")
    assert other.update(tracking_request(0, source_id="camera-b")).source_id == "camera-b"


def test_reset_clears_identity_state_and_close_is_idempotent() -> None:
    tracker = DeterministicIoUTracker()
    tracker.start("camera")
    tracker.update(tracking_request(0, (pig_detection(),)))
    tracker.reset()
    result = tracker.update(tracking_request(0, (pig_detection(),)))
    tracker.close()
    tracker.close()

    assert result.tracked_objects[0].track.tracker_id == 0
    assert tracker.reset_count == 1
    assert tracker.close_count == 1
    assert not tracker.is_started


def test_stale_frame_and_unstarted_updates_are_rejected() -> None:
    tracker = EmptyTracker()
    with pytest.raises(TrackerLifecycleError):
        tracker.update(tracking_request(0))
    tracker.start("camera")
    tracker.update(tracking_request(2))
    with pytest.raises(StaleTrackingRequestError):
        tracker.update(tracking_request(2))


def test_slow_and_failing_trackers_are_deterministic() -> None:
    delays: list[float] = []
    slow = SlowTracker(delay_seconds=0.25, sleeper=delays.append)
    slow.start("camera")
    slow.update(tracking_request(0))
    assert delays == [0.25]

    failing = FailingTracker(temporary_sequences=(1,), fatal_sequences=(2,))
    failing.start("camera")
    with pytest.raises(TemporaryTrackingError):
        failing.update(tracking_request(1))
    with pytest.raises(FatalTrackingError):
        failing.update(tracking_request(2))


def test_malformed_detection_is_rejected_before_tracker_state() -> None:
    with pytest.raises(InputDataError):
        tracking_request(0, (pig_detection(x_max=float("nan")),))
