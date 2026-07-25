import inspect
from typing import get_type_hints

from _phase7_helpers import counting_configuration

from hogflow.counting import LifecycleDirectionalCounter, LiveDirectionalCounter


def test_live_directional_counter_protocol_is_small_typed_and_documented() -> None:
    assert inspect.isclass(LiveDirectionalCounter)
    assert LiveDirectionalCounter.__doc__
    for name in (
        "configuration",
        "is_started",
        "source_id",
        "crossing_lifecycle_id",
        "counting_lifecycle_id",
        "start",
        "update",
        "reset",
        "close",
        "statistics",
    ):
        member = getattr(LiveDirectionalCounter, name)
        assert member.__doc__
        target = member.fget if isinstance(member, property) else member
        assert get_type_hints(target)


def test_lifecycle_counter_structurally_exposes_the_generic_contract() -> None:
    counter: LiveDirectionalCounter = LifecycleDirectionalCounter(counting_configuration())

    assert not counter.is_started
    counter.start("camera", "crossing-lifecycle-1")
    assert counter.is_started
    counter.reset("crossing-lifecycle-2")
    counter.close()
    assert not counter.is_started
