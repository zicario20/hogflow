from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from hogflow.domain import DockId
from hogflow.sessions import (
    FinalizedSessionCountingLifecycle,
    SessionCountingIntegrationError,
    SessionCountingLifecycle,
    SessionCountingOutcome,
)

BASE = datetime(2026, 7, 25, tzinfo=timezone.utc)


def lifecycle() -> SessionCountingLifecycle:
    return SessionCountingLifecycle(
        operation_id="operation-1",
        dock_id=DockId.DOCK_1,
        session_id="session-1",
        source_id="camera",
        crossing_lifecycle_id="crossing-lifecycle-1",
        counting_lifecycle_id="counting-lifecycle-1",
        counting_configuration_fingerprint="a" * 64,
        started_at=BASE,
    )


def test_session_counting_lifecycle_is_validated_and_immutable() -> None:
    value = lifecycle()

    assert value.dock_id is DockId.DOCK_1
    assert value.session_id == "session-1"
    with pytest.raises(FrozenInstanceError):
        value.session_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("source_id", "camera/path", "source ID"),
        ("crossing_lifecycle_id", "", "Crossing lifecycle"),
        ("counting_lifecycle_id", "contains space", "Counting lifecycle"),
        ("counting_configuration_fingerprint", "short", "SHA-256"),
        ("started_at", datetime(2026, 7, 25), "timezone-aware"),
    ),
)
def test_session_counting_lifecycle_rejects_invalid_provenance(
    field: str,
    value: object,
    message: str,
) -> None:
    values = {
        "operation_id": "operation-1",
        "dock_id": DockId.DOCK_1,
        "session_id": "session-1",
        "source_id": "camera",
        "crossing_lifecycle_id": "crossing-lifecycle-1",
        "counting_lifecycle_id": "counting-lifecycle-1",
        "counting_configuration_fingerprint": "a" * 64,
        "started_at": BASE,
    }
    values[field] = value

    with pytest.raises(SessionCountingIntegrationError, match=message):
        SessionCountingLifecycle(**values)  # type: ignore[arg-type]


def test_completed_finalization_requires_non_negative_count() -> None:
    finalization = FinalizedSessionCountingLifecycle(
        lifecycle=lifecycle(),
        outcome=SessionCountingOutcome.COMPLETED,
        finalized_count=0,
        ended_at=BASE + timedelta(seconds=1),
    )

    assert finalization.finalized_count == 0
    with pytest.raises(SessionCountingIntegrationError, match="non-negative"):
        FinalizedSessionCountingLifecycle(
            lifecycle=lifecycle(),
            outcome=SessionCountingOutcome.COMPLETED,
            finalized_count=-1,
            ended_at=BASE + timedelta(seconds=1),
        )


def test_cancelled_finalization_discards_count_and_end_must_follow_start() -> None:
    finalization = FinalizedSessionCountingLifecycle(
        lifecycle=lifecycle(),
        outcome=SessionCountingOutcome.CANCELLED,
        finalized_count=None,
        ended_at=BASE + timedelta(seconds=1),
    )

    assert finalization.finalized_count is None
    with pytest.raises(SessionCountingIntegrationError, match="discard"):
        FinalizedSessionCountingLifecycle(
            lifecycle=lifecycle(),
            outcome=SessionCountingOutcome.CANCELLED,
            finalized_count=1,
            ended_at=BASE + timedelta(seconds=1),
        )
    with pytest.raises(SessionCountingIntegrationError, match="precede"):
        FinalizedSessionCountingLifecycle(
            lifecycle=lifecycle(),
            outcome=SessionCountingOutcome.CANCELLED,
            finalized_count=None,
            ended_at=BASE - timedelta(seconds=1),
        )
