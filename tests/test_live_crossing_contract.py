import inspect
from typing import get_type_hints

from hogflow.counting import (
    LiveCrossingConfiguration,
    LiveCrossingDetector,
    NormalizedLine,
    NormalizedPoint,
    VirtualLineCrossingDetector,
)


def test_live_crossing_protocol_is_small_typed_and_documented() -> None:
    assert inspect.isclass(LiveCrossingDetector)
    assert LiveCrossingDetector.__doc__
    for name in ("configuration", "is_started", "start", "update", "reset", "close"):
        member = getattr(LiveCrossingDetector, name)
        assert member.__doc__
        target = member.fget if isinstance(member, property) else member
        assert get_type_hints(target)


def test_virtual_line_crossing_detector_structurally_exposes_lifecycle_contract() -> None:
    detector = VirtualLineCrossingDetector(
        LiveCrossingConfiguration(
            enabled=True,
            line=NormalizedLine(NormalizedPoint(0, 0.5), NormalizedPoint(1, 0.5)),
        )
    )

    assert not detector.is_started
    detector.start("camera")
    assert detector.is_started
    detector.reset()
    detector.close()
    assert not detector.is_started
