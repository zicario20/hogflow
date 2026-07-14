import inspect
from collections.abc import Sequence
from typing import get_type_hints

from hogflow.models import Detection, Frame, Track
from hogflow.tracking import Tracker
from hogflow.tracking import contracts as tracker_contracts


def test_exactly_one_tracker_protocol_is_public() -> None:
    public_classes = [
        value
        for name, value in vars(tracker_contracts).items()
        if inspect.isclass(value) and value.__module__ == tracker_contracts.__name__
    ]

    assert public_classes == [Tracker]
    assert getattr(Tracker, "_is_protocol", False) is True
    assert tracker_contracts.__all__ == ["Tracker"]


def test_tracker_protocol_uses_only_shared_contract_models() -> None:
    hints = get_type_hints(Tracker.update)

    assert hints == {
        "frame": Frame,
        "detections": Sequence[Detection],
        "return": Sequence[Track],
    }


def test_tracker_public_api_is_documented_and_typed() -> None:
    assert inspect.getdoc(Tracker)
    assert inspect.getdoc(Tracker.update)
    assert inspect.signature(Tracker.update).return_annotation != inspect.Signature.empty
