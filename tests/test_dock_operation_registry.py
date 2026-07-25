from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from hogflow.domain import (
    DockId,
    DockOccupiedError,
    DockOperationRegistry,
    DuplicateOperationIdError,
    InvalidDockError,
    OperationNotFoundError,
    PigType,
    TruckOperation,
    TruckOperationStatus,
    UnloadingSession,
    UnloadingSessionStatus,
)

BASE = datetime(2026, 7, 25, 10, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return BASE + timedelta(minutes=minutes)


def operation(
    dock_id: DockId,
    operation_id: str,
    pig_type: PigType,
    *,
    session_id: str = "session-1",
) -> TruckOperation:
    return TruckOperation(operation_id, dock_id).add_session(
        UnloadingSession(session_id, 1, pig_type)
    )


def complete_current(
    registry: DockOperationRegistry,
    dock_id: DockId,
    count: int,
) -> DockOperationRegistry:
    registry = registry.start_operation(dock_id, at(0))
    registry = registry.start_session(dock_id, "session-1", at(1))
    registry = registry.complete_session(dock_id, "session-1", count, at(2))
    return registry.complete_operation(dock_id, at(3))


def test_new_registry_reports_all_four_docks_available() -> None:
    registry = DockOperationRegistry()
    assert tuple(registry.is_available(dock_id) for dock_id in DockId) == (
        True,
        True,
        True,
        True,
    )


def test_non_terminal_operation_occupies_only_its_dock() -> None:
    registry = DockOperationRegistry().register_operation(
        operation(DockId.DOCK_1, "operation-1", PigType.REGULAR)
    )

    assert not registry.is_available(DockId.DOCK_1)
    assert registry.is_available(DockId.DOCK_2)
    assert registry.operation_for(DockId.DOCK_1) is not None


def test_second_non_terminal_operation_at_same_dock_is_rejected_atomically() -> None:
    original = DockOperationRegistry().register_operation(
        operation(DockId.DOCK_1, "operation-1", PigType.REGULAR)
    )
    with pytest.raises(DockOccupiedError, match="dock_1"):
        original.register_operation(operation(DockId.DOCK_1, "operation-2", PigType.OPG))

    assert original.operation_for(DockId.DOCK_1).operation_id == "operation-1"  # type: ignore[union-attr]
    assert len(original.operations) == 1


def test_operation_ids_must_be_unique_across_current_dock_records() -> None:
    registry = DockOperationRegistry().register_operation(
        operation(DockId.DOCK_1, "operation-shared", PigType.REGULAR)
    )
    with pytest.raises(DuplicateOperationIdError, match="another current dock"):
        registry.register_operation(operation(DockId.DOCK_2, "operation-shared", PigType.OPG))


def test_completion_makes_dock_available_and_allows_replacement() -> None:
    registry = DockOperationRegistry().register_operation(
        operation(DockId.DOCK_1, "operation-1", PigType.REGULAR)
    )
    completed = complete_current(registry, DockId.DOCK_1, 55)

    assert completed.is_available(DockId.DOCK_1)
    assert completed.operation_for(DockId.DOCK_1).truck_total == 55  # type: ignore[union-attr]

    replacement = completed.register_operation(operation(DockId.DOCK_1, "operation-2", PigType.OPG))
    assert replacement.operation_for(DockId.DOCK_1).operation_id == "operation-2"  # type: ignore[union-attr]
    assert not replacement.is_available(DockId.DOCK_1)


def test_cancellation_makes_dock_available() -> None:
    registry = DockOperationRegistry().register_operation(
        operation(DockId.DOCK_1, "operation-1", PigType.REGULAR)
    )
    cancelled = registry.cancel_operation(DockId.DOCK_1, at(1))

    assert cancelled.is_available(DockId.DOCK_1)
    assert (
        cancelled.operation_for(DockId.DOCK_1).status  # type: ignore[union-attr]
        is TruckOperationStatus.CANCELLED
    )


def test_four_docks_operate_with_isolated_state() -> None:
    registry = DockOperationRegistry()
    registry = registry.register_operation(operation(DockId.DOCK_1, "operation-1", PigType.REGULAR))
    registry = registry.register_operation(operation(DockId.DOCK_2, "operation-2", PigType.OPG))
    registry = registry.register_operation(operation(DockId.DOCK_3, "operation-3", PigType.P12))

    dock_2_before = registry.operation_for(DockId.DOCK_2)
    registry_after_dock_1_add = registry.add_session(
        DockId.DOCK_1,
        UnloadingSession("session-2", 2, PigType.REGULAR),
    )
    assert len(registry_after_dock_1_add.operation_for(DockId.DOCK_1).sessions) == 2  # type: ignore[union-attr]
    assert registry_after_dock_1_add.operation_for(DockId.DOCK_2) == dock_2_before

    dock_1_completed = complete_current(registry, DockId.DOCK_1, 55)
    assert dock_1_completed.operation_for(DockId.DOCK_1).truck_total == 55  # type: ignore[union-attr]
    assert (
        dock_1_completed.operation_for(DockId.DOCK_2).status  # type: ignore[union-attr]
        is TruckOperationStatus.PLANNED
    )

    dock_3_cancelled = dock_1_completed.cancel_operation(DockId.DOCK_3, at(4))
    assert (
        dock_3_cancelled.operation_for(DockId.DOCK_3).status  # type: ignore[union-attr]
        is TruckOperationStatus.CANCELLED
    )
    assert dock_3_cancelled.operation_for(DockId.DOCK_1).truck_total == 55  # type: ignore[union-attr]
    assert dock_3_cancelled.operation_for(DockId.DOCK_2) == dock_2_before
    assert dock_3_cancelled.is_available(DockId.DOCK_4)


def test_same_session_id_is_isolated_between_operations() -> None:
    registry = DockOperationRegistry(
        (
            operation(
                DockId.DOCK_1,
                "operation-1",
                PigType.REGULAR,
                session_id="shared-session",
            ),
            operation(
                DockId.DOCK_2,
                "operation-2",
                PigType.OPG,
                session_id="shared-session",
            ),
        )
    )
    assert (
        registry.operation_for(DockId.DOCK_1).session("shared-session").pig_type is PigType.REGULAR
    )  # type: ignore[union-attr]
    assert registry.operation_for(DockId.DOCK_2).session("shared-session").pig_type is PigType.OPG  # type: ignore[union-attr]


def test_registry_delegates_session_lifecycle_without_cross_dock_mutation() -> None:
    registry = DockOperationRegistry(
        (
            operation(DockId.DOCK_1, "operation-1", PigType.REGULAR),
            operation(DockId.DOCK_2, "operation-2", PigType.OPG),
        )
    )
    dock_2_original = registry.operation_for(DockId.DOCK_2)

    updated = registry.start_operation(DockId.DOCK_1, at(0))
    updated = updated.start_session(DockId.DOCK_1, "session-1", at(1))
    updated = updated.complete_session(DockId.DOCK_1, "session-1", 61, at(2))

    assert (
        updated.operation_for(DockId.DOCK_1).session("session-1").status  # type: ignore[union-attr]
        is UnloadingSessionStatus.COMPLETED
    )
    assert updated.operation_for(DockId.DOCK_2) == dock_2_original


def test_missing_operation_and_invalid_dock_are_explicit_errors() -> None:
    registry = DockOperationRegistry()
    with pytest.raises(OperationNotFoundError, match="dock_1"):
        registry.start_operation(DockId.DOCK_1, at(0))
    with pytest.raises(InvalidDockError, match="supported dock"):
        registry.is_available("dock_1")  # type: ignore[arg-type]


def test_registry_is_immutable_and_deterministically_ordered() -> None:
    registry = DockOperationRegistry(
        (
            operation(DockId.DOCK_3, "operation-3", PigType.P12),
            operation(DockId.DOCK_1, "operation-1", PigType.REGULAR),
        )
    )

    assert tuple(item.dock_id for item in registry.operations) == (
        DockId.DOCK_1,
        DockId.DOCK_3,
    )
    with pytest.raises(FrozenInstanceError):
        registry.operations = ()  # type: ignore[misc]
