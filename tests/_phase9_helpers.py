from __future__ import annotations

from datetime import datetime, timedelta, timezone

from _phase7_helpers import counting_configuration, crossing_event, crossing_result

from hogflow.application import (
    DockId,
    OperatorApplicationService,
    PigType,
    PlannedSession,
    RegisterTruckCommand,
)
from hogflow.counting import LifecycleDirectionalCounter, LiveCrossingDirection
from hogflow.sessions import MultiDockRuntimeCoordinator, SharedCountingLane

BASE = datetime(2026, 7, 26, tzinfo=timezone.utc)
SOURCE_ID = "shared_operator_lane"


class StepClock:
    def __init__(self, *, seconds_per_step: int = 1) -> None:
        self._step = 0
        self._seconds_per_step = seconds_per_step

    def __call__(self) -> datetime:
        value = BASE + timedelta(seconds=self._step * self._seconds_per_step)
        self._step += 1
        return value


class LifecycleIdFactory:
    def __init__(self) -> None:
        self._generation = 0

    def __call__(self, dock_id: DockId, session_id: str) -> str:
        self._generation += 1
        return f"operator-{dock_id.value}-{session_id}-{self._generation}"


def operator_application() -> tuple[
    OperatorApplicationService,
    MultiDockRuntimeCoordinator,
]:
    counter = LifecycleDirectionalCounter(counting_configuration())
    lane = SharedCountingLane(counter, source_id=SOURCE_ID)
    coordinator = MultiDockRuntimeCoordinator(lane, clock=StepClock(seconds_per_step=100))
    application = OperatorApplicationService(
        coordinator,
        crossing_lifecycle_id_factory=LifecycleIdFactory(),
        clock=StepClock(seconds_per_step=100),
    )
    return application, coordinator


def registration(
    dock_id: DockId = DockId.DOCK_1,
    pig_types: tuple[PigType, ...] = (PigType.REGULAR,),
    *,
    operation_id: str | None = None,
) -> RegisterTruckCommand:
    return RegisterTruckCommand(
        dock_id=dock_id,
        operation_id=operation_id or f"operator-{dock_id.value}",
        sessions=tuple(
            PlannedSession(
                session_id=f"{dock_id.value}-session-{sequence}",
                sequence_number=sequence,
                pig_type=pig_type,
            )
            for sequence, pig_type in enumerate(pig_types, start=1)
        ),
    )


def add_positive_count(
    coordinator: MultiDockRuntimeCoordinator,
    dock_id: DockId,
    tracker_ids: tuple[int, ...],
    *,
    frame_sequence: int = 1,
) -> None:
    lane = coordinator.snapshot().counting_lane
    assert lane.crossing_lifecycle_id is not None
    captured_at = BASE + timedelta(seconds=150 + frame_sequence)
    events = tuple(
        crossing_event(
            frame_sequence,
            tracker_id,
            LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
            source_id=SOURCE_ID,
            lifecycle_id=lane.crossing_lifecycle_id,
            captured_at=captured_at,
        )
        for tracker_id in tracker_ids
    )
    coordinator.process_counting_result(
        dock_id,
        crossing_result(
            frame_sequence,
            events,
            source_id=SOURCE_ID,
            lifecycle_id=lane.crossing_lifecycle_id,
            captured_at=captured_at,
        ),
    )
