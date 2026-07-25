from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from hogflow.domain import (
    DockId,
    InvalidCountError,
    InvalidDockError,
    InvalidPigTypeError,
    InvalidSessionTransitionError,
    InvalidTimestampError,
    PigType,
    TruckOperationStatus,
    UnloadingSession,
    UnloadingSessionStatus,
    UnloadingSessionSummary,
)

NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


def test_all_supported_pig_types_have_stable_values() -> None:
    assert tuple((item.name, item.value) for item in PigType) == (
        ("REGULAR", "regular"),
        ("OPG", "opg"),
        ("P12", "p12"),
        ("NAE", "nae"),
    )
    assert PigType.P12.value == "p12"


def test_pig_type_parse_rejects_unsupported_values() -> None:
    assert PigType.parse("regular") is PigType.REGULAR
    with pytest.raises(InvalidPigTypeError, match="regular, opg, p12, or nae"):
        PigType.parse("p-12")


def test_exactly_four_supported_dock_ids_exist() -> None:
    assert tuple((item.name, item.value) for item in DockId) == (
        ("DOCK_1", "dock_1"),
        ("DOCK_2", "dock_2"),
        ("DOCK_3", "dock_3"),
        ("DOCK_4", "dock_4"),
    )
    assert tuple(item.sequence_number for item in DockId) == (1, 2, 3, 4)


def test_dock_parse_rejects_unsupported_identifiers() -> None:
    assert DockId.parse("dock_4") is DockId.DOCK_4
    for value in ("dock_5", 1, True):
        with pytest.raises(InvalidDockError, match="dock_1"):
            DockId.parse(value)


def test_session_creation_accepts_optional_expected_count() -> None:
    session = UnloadingSession(
        session_id="session-1",
        sequence_number=1,
        pig_type=PigType.OPG,
        expected_count=60,
    )

    assert session.status is UnloadingSessionStatus.PLANNED
    assert session.expected_count == 60
    assert session.actual_count == 0
    assert session.started_at is None
    assert session.ended_at is None


@pytest.mark.parametrize("sequence_number", (0, -1, True))
def test_session_sequence_must_be_a_positive_integer(sequence_number: object) -> None:
    with pytest.raises(InvalidSessionTransitionError, match="positive integer"):
        UnloadingSession(
            session_id="session-1",
            sequence_number=sequence_number,  # type: ignore[arg-type]
            pig_type=PigType.REGULAR,
        )


def test_session_requires_explicit_supported_pig_type() -> None:
    with pytest.raises(InvalidPigTypeError, match="explicit"):
        UnloadingSession(
            session_id="session-1",
            sequence_number=1,
            pig_type="regular",  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("value", (-1, True))
def test_negative_or_boolean_expected_count_is_rejected(value: object) -> None:
    with pytest.raises(InvalidCountError, match="Expected count"):
        UnloadingSession(
            session_id="session-1",
            sequence_number=1,
            pig_type=PigType.REGULAR,
            expected_count=value,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("value", (-1, True))
def test_negative_or_boolean_actual_count_is_rejected(value: object) -> None:
    with pytest.raises(InvalidCountError, match="Actual count"):
        UnloadingSession(
            session_id="session-1",
            sequence_number=1,
            pig_type=PigType.REGULAR,
            actual_count=value,  # type: ignore[arg-type]
        )


def test_actual_count_cannot_be_assigned_before_completion() -> None:
    with pytest.raises(InvalidCountError, match="only when a session completes"):
        UnloadingSession(
            session_id="session-1",
            sequence_number=1,
            pig_type=PigType.REGULAR,
            actual_count=10,
        )


def test_session_lifecycle_requires_aware_consistent_timestamps() -> None:
    naive = datetime(2026, 7, 25, 12, 0)
    with pytest.raises(InvalidTimestampError, match="timezone-aware"):
        UnloadingSession(
            session_id="session-1",
            sequence_number=1,
            pig_type=PigType.REGULAR,
            status=UnloadingSessionStatus.ACTIVE,
            started_at=naive,
        )
    with pytest.raises(InvalidTimestampError, match="cannot precede"):
        UnloadingSession(
            session_id="session-1",
            sequence_number=1,
            pig_type=PigType.REGULAR,
            status=UnloadingSessionStatus.COMPLETED,
            started_at=NOW,
            ended_at=NOW - timedelta(seconds=1),
        )


def test_status_timestamp_combinations_are_validated() -> None:
    with pytest.raises(InvalidSessionTransitionError, match="planned"):
        UnloadingSession(
            session_id="session-1",
            sequence_number=1,
            pig_type=PigType.REGULAR,
            started_at=NOW,
        )
    with pytest.raises(InvalidSessionTransitionError, match="requires a start"):
        UnloadingSession(
            session_id="session-1",
            sequence_number=1,
            pig_type=PigType.REGULAR,
            status=UnloadingSessionStatus.ACTIVE,
        )
    with pytest.raises(InvalidSessionTransitionError, match="requires start and end"):
        UnloadingSession(
            session_id="session-1",
            sequence_number=1,
            pig_type=PigType.REGULAR,
            status=UnloadingSessionStatus.COMPLETED,
        )


def test_session_summary_validates_its_public_fields() -> None:
    with pytest.raises(InvalidCountError, match="Actual count"):
        UnloadingSessionSummary(
            session_id="session-1",
            sequence_number=1,
            pig_type=PigType.REGULAR,
            status=UnloadingSessionStatus.PLANNED,
            expected_count=None,
            actual_count=-1,
            started_at=None,
            ended_at=None,
        )


def test_session_start_complete_and_summary_are_copy_on_write() -> None:
    planned = UnloadingSession("session-1", 1, PigType.P12, expected_count=10)
    active = planned.start(NOW)
    completed = active.complete(10, NOW + timedelta(minutes=1))
    summary = completed.summary()

    assert planned.status is UnloadingSessionStatus.PLANNED
    assert active.status is UnloadingSessionStatus.ACTIVE
    assert completed.status is UnloadingSessionStatus.COMPLETED
    assert completed.actual_count == 10
    assert summary.actual_count == 10
    assert summary.pig_type is PigType.P12


def test_zero_is_a_valid_completed_session_count() -> None:
    completed = (
        UnloadingSession("session-1", 1, PigType.NAE)
        .start(NOW)
        .complete(
            0,
            NOW + timedelta(minutes=1),
        )
    )
    assert completed.actual_count == 0


def test_cancelled_session_is_terminal_and_cannot_restart() -> None:
    cancelled = UnloadingSession("session-1", 1, PigType.NAE).cancel(NOW)

    assert cancelled.status is UnloadingSessionStatus.CANCELLED
    with pytest.raises(InvalidSessionTransitionError, match="planned"):
        cancelled.start(NOW + timedelta(minutes=1))


def test_domain_models_and_enums_are_immutable_or_stable() -> None:
    session = UnloadingSession("session-1", 1, PigType.REGULAR)
    with pytest.raises(FrozenInstanceError):
        session.actual_count = 1  # type: ignore[misc]
    assert TruckOperationStatus.COMPLETED.is_terminal
    assert UnloadingSessionStatus.CANCELLED.is_terminal
