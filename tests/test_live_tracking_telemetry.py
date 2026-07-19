from _phase5_3_helpers import pig_detection, tracking_request

from hogflow.tracking import (
    DeterministicIoUTracker,
    LiveTrackingTelemetry,
    TrackingErrorCategory,
    TrackingHealthState,
)


def test_tracking_telemetry_records_bounded_aggregates_not_history() -> None:
    tracker = DeterministicIoUTracker()
    tracker.start("camera")
    telemetry = LiveTrackingTelemetry()
    telemetry.record_starting()
    telemetry.record_started()

    request = tracking_request(0, (pig_detection(),))
    telemetry.record_request(request)
    telemetry.record_success(tracker.update(request))
    telemetry.record_stopping()
    telemetry.record_closed()

    statistics = telemetry.snapshot()
    assert statistics.tracking_requests == 1
    assert statistics.tracking_successes == 1
    assert statistics.tracks_emitted == 1
    assert statistics.active_tracks_current == 0
    assert statistics.active_tracks_peak == 1
    assert statistics.current_health_state is TrackingHealthState.STOPPED
    assert not hasattr(telemetry, "_history")


def test_tracking_telemetry_separates_update_and_lifecycle_failures() -> None:
    telemetry = LiveTrackingTelemetry()
    request = tracking_request(3)
    telemetry.record_request(request)
    telemetry.record_failure(TrackingErrorCategory.STALE, fatal=True, stale=True)
    telemetry.record_lifecycle_failure(TrackingErrorCategory.CLOSE, fatal=True)
    telemetry.record_preview_failure()

    statistics = telemetry.snapshot()
    assert statistics.tracking_failures == 1
    assert statistics.lifecycle_failures == 1
    assert statistics.stale_requests_rejected == 1
    assert statistics.preview_failures == 1
    assert statistics.last_tracking_error is TrackingErrorCategory.CLOSE
