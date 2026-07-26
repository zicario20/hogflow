from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from _phase7_helpers import counting_configuration, crossing_event, crossing_result

from hogflow.counting import (
    LifecycleDirectionalCounter,
    LiveCrossingDirection,
)
from hogflow.domain import DockId, PigType, TruckOperation, UnloadingSession
from hogflow.sessions import (
    CountingLaneClosedError,
    CountingLaneNotBoundError,
    CountingLaneOccupiedError,
    CountingLaneOwnershipError,
    CountingLaneShutdownError,
    SessionCountingOutcome,
    SharedCountingLane,
)

BASE = datetime(2026, 7, 25, tzinfo=timezone.utc)
SOURCE_ID = "shared_lane"


def at(seconds: int) -> datetime:
    return BASE + timedelta(seconds=seconds)


def active_operation(dock_id: DockId, session_id: str) -> TruckOperation:
    return (
        TruckOperation(f"operation-{dock_id.value}", dock_id)
        .add_session(UnloadingSession(session_id, 1, PigType.REGULAR))
        .start(at(0))
    )


def test_lane_binds_one_operation_and_exposes_immutable_provenance() -> None:
    counter = LifecycleDirectionalCounter(counting_configuration())
    lane = SharedCountingLane(counter, source_id=SOURCE_ID)

    lifecycle = lane.bind(
        DockId.DOCK_1,
        active_operation(DockId.DOCK_1, "session-1"),
        (),
        "session-1",
        "crossing-1",
        at(1),
    )
    snapshot = lane.snapshot()

    assert lifecycle.source_id == SOURCE_ID
    assert snapshot.occupied
    assert snapshot.active_dock_id is DockId.DOCK_1
    assert snapshot.active_session_id == "session-1"
    assert counter.is_started


def test_lane_rejects_second_binding_and_wrong_owner() -> None:
    counter = LifecycleDirectionalCounter(counting_configuration())
    lane = SharedCountingLane(counter, source_id=SOURCE_ID)
    lane.bind(
        DockId.DOCK_1,
        active_operation(DockId.DOCK_1, "session-1"),
        (),
        "session-1",
        "crossing-1",
        at(1),
    )

    with pytest.raises(CountingLaneOccupiedError):
        lane.bind(
            DockId.DOCK_2,
            active_operation(DockId.DOCK_2, "session-2"),
            (),
            "session-2",
            "crossing-2",
            at(1),
        )
    with pytest.raises(CountingLaneOwnershipError):
        lane.process(
            DockId.DOCK_2,
            crossing_result(
                1,
                (),
                source_id=SOURCE_ID,
                lifecycle_id="crossing-1",
                captured_at=at(2),
            ),
        )


def test_complete_releases_lane_with_finalized_count() -> None:
    counter = LifecycleDirectionalCounter(counting_configuration())
    lane = SharedCountingLane(counter, source_id=SOURCE_ID)
    lane.bind(
        DockId.DOCK_1,
        active_operation(DockId.DOCK_1, "session-1"),
        (),
        "session-1",
        "crossing-1",
        at(1),
    )
    event = crossing_event(
        1,
        42,
        LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
        source_id=SOURCE_ID,
        lifecycle_id="crossing-1",
        captured_at=at(2),
    )
    lane.process(
        DockId.DOCK_1,
        crossing_result(
            1,
            (event,),
            source_id=SOURCE_ID,
            lifecycle_id="crossing-1",
            captured_at=at(2),
        ),
    )

    release = lane.complete(DockId.DOCK_1, at(3))

    assert release.finalization.outcome is SessionCountingOutcome.COMPLETED
    assert release.finalization.finalized_count == 1
    assert not lane.is_bound
    assert lane.snapshot().current_session_count == 0


def test_cancel_releases_lane_without_transferring_live_count() -> None:
    counter = LifecycleDirectionalCounter(counting_configuration())
    lane = SharedCountingLane(counter, source_id=SOURCE_ID)
    lane.bind(
        DockId.DOCK_1,
        active_operation(DockId.DOCK_1, "session-1"),
        (),
        "session-1",
        "crossing-1",
        at(1),
    )

    release = lane.cancel(DockId.DOCK_1, at(2))

    assert release.finalization.outcome is SessionCountingOutcome.CANCELLED
    assert release.finalization.finalized_count is None
    assert not lane.is_bound


def test_idle_lane_rejects_processing_and_can_close_idempotently() -> None:
    counter = LifecycleDirectionalCounter(counting_configuration())
    lane = SharedCountingLane(counter, source_id=SOURCE_ID)
    result = crossing_result(
        1,
        (),
        source_id=SOURCE_ID,
        lifecycle_id="crossing-1",
        captured_at=at(1),
    )

    with pytest.raises(CountingLaneNotBoundError):
        lane.process(DockId.DOCK_1, result)
    assert lane.close() is None
    assert lane.close() is None
    assert lane.is_closed
    with pytest.raises(CountingLaneClosedError):
        lane.bind(
            DockId.DOCK_1,
            active_operation(DockId.DOCK_1, "session-1"),
            (),
            "session-1",
            "crossing-1",
            at(1),
        )


def test_occupied_lane_requires_explicit_cancellation_timestamp_to_close() -> None:
    counter = LifecycleDirectionalCounter(counting_configuration())
    lane = SharedCountingLane(counter, source_id=SOURCE_ID)
    lane.bind(
        DockId.DOCK_1,
        active_operation(DockId.DOCK_1, "session-1"),
        (),
        "session-1",
        "crossing-1",
        at(1),
    )

    with pytest.raises(CountingLaneShutdownError):
        lane.close()

    assert lane.is_bound
    assert not lane.is_closed
