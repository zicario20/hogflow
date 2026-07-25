from dataclasses import FrozenInstanceError, replace
from datetime import datetime

import pytest
from _phase7_helpers import (
    BASE_TIMESTAMP,
    CROSSING_FINGERPRINT,
    counting_configuration,
    crossing_event,
    crossing_result,
)

from hogflow.core import ConfigurationError, InputDataError
from hogflow.counting import (
    CountingDecisionType,
    LifecycleDirectionalCounter,
    LiveCountingConfiguration,
    LiveCrossingDirection,
    OperationalCrossingDirection,
    TemporaryTrackIdentity,
)


def test_counting_is_disabled_by_default_and_configuration_is_immutable() -> None:
    disabled = LiveCountingConfiguration()
    enabled = counting_configuration()

    assert not disabled.enabled
    assert enabled.positive_direction is LiveCrossingDirection.NEGATIVE_TO_POSITIVE
    with pytest.raises(FrozenInstanceError):
        enabled.maximum_counted_identities = 2  # type: ignore[misc]


@pytest.mark.parametrize(
    "arguments",
    (
        {"enabled": True},
        {"enabled": False, "positive_direction": LiveCrossingDirection.NEGATIVE_TO_POSITIVE},
        {
            "enabled": True,
            "positive_direction": "negative_to_positive",
            "crossing_configuration_fingerprint": CROSSING_FINGERPRINT,
        },
        {
            "enabled": True,
            "positive_direction": LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
            "crossing_configuration_fingerprint": "invalid",
        },
        {"maximum_counted_identities": 0},
        {"maximum_counted_identities": True},
    ),
)
def test_counting_configuration_rejects_incomplete_or_invalid_values(
    arguments: dict[str, object],
) -> None:
    with pytest.raises(ConfigurationError):
        LiveCountingConfiguration(**arguments)  # type: ignore[arg-type]


def test_configuration_fingerprint_is_stable_and_sensitive() -> None:
    first = counting_configuration()
    same = counting_configuration()
    reversed_direction = counting_configuration(
        positive_direction=LiveCrossingDirection.POSITIVE_TO_NEGATIVE
    )

    assert first.fingerprint == same.fingerprint
    assert first.fingerprint != reversed_direction.fingerprint
    assert len(first.fingerprint) == 64


def test_temporary_identity_is_hashable_immutable_and_lifecycle_qualified() -> None:
    identity = TemporaryTrackIdentity("camera", "crossing-lifecycle-1", 7)
    same = TemporaryTrackIdentity("camera", "crossing-lifecycle-1", 7)
    new_lifecycle = TemporaryTrackIdentity("camera", "crossing-lifecycle-2", 7)

    assert hash(identity) == hash(same)
    assert identity != new_lifecycle
    with pytest.raises(FrozenInstanceError):
        identity.tracker_id = 9  # type: ignore[misc]


@pytest.mark.parametrize(
    "arguments",
    (
        ("bad source", "crossing-lifecycle-1", 1),
        ("camera", "bad lifecycle!", 1),
        ("camera", "crossing-lifecycle-1", -1),
        ("camera", "crossing-lifecycle-1", True),
    ),
)
def test_temporary_identity_rejects_invalid_fields(arguments: tuple[object, ...]) -> None:
    with pytest.raises(InputDataError):
        TemporaryTrackIdentity(*arguments)  # type: ignore[arg-type]


def test_counting_decision_and_result_are_coherent_and_immutable() -> None:
    counter = LifecycleDirectionalCounter(counting_configuration())
    counter.start("camera", "crossing-lifecycle-1")
    event = crossing_event(
        1,
        4,
        LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
    )
    result = counter.update(crossing_result(1, (event,)))
    decision = result.decisions[0]

    assert decision.decision_type is CountingDecisionType.COUNTED_POSITIVE
    assert decision.crossing_event == event
    assert decision.operational_direction is OperationalCrossingDirection.POSITIVE
    assert decision.count_increment == 1
    assert decision.total_before == 0
    assert decision.total_after == 1
    assert result.frame_increments == 1
    assert result.lifecycle_directional_count == 1
    with pytest.raises(FrozenInstanceError):
        result.frame_increments = 0  # type: ignore[misc]


def test_decision_rejects_invalid_increment_total_and_naive_timestamp() -> None:
    counter = LifecycleDirectionalCounter(counting_configuration())
    counter.start("camera", "crossing-lifecycle-1")
    result = counter.update(
        crossing_result(
            1,
            (
                crossing_event(
                    1,
                    1,
                    LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
                ),
            ),
        )
    )
    decision = result.decisions[0]

    with pytest.raises(InputDataError, match="zero or one"):
        replace(decision, count_increment=2)
    with pytest.raises(InputDataError, match="total"):
        replace(decision, total_after=4)
    with pytest.raises(InputDataError, match="timezone"):
        replace(decision, captured_at=datetime(2026, 7, 25))


def test_crossing_lifecycle_alias_is_explicit_and_compatible() -> None:
    event = crossing_event(
        1,
        1,
        LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
    )
    result = crossing_result(1, (event,))

    assert event.crossing_lifecycle_id == event.tracker_lifecycle_id
    assert result.crossing_lifecycle_id == result.tracker_lifecycle_id
    assert event.captured_at == BASE_TIMESTAMP.replace(second=1)
