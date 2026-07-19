from typing import get_type_hints

from hogflow.tracking import LiveTracker, TrackingRequest, TrackingResult


def test_live_tracker_protocol_exposes_only_lifecycle_and_update_contract() -> None:
    assert set(LiveTracker.__dict__) & {
        "metadata",
        "is_started",
        "start",
        "update",
        "reset",
        "close",
    } == {"metadata", "is_started", "start", "update", "reset", "close"}
    assert "count" not in LiveTracker.__dict__


def test_live_tracker_update_uses_framework_neutral_types() -> None:
    hints = get_type_hints(LiveTracker.update)

    assert hints["request"] is TrackingRequest
    assert hints["return"] is TrackingResult
    assert LiveTracker.__doc__
    assert LiveTracker.update.__doc__
