import inspect
from collections.abc import Sequence
from typing import get_type_hints

from hogflow.detection import Detector
from hogflow.detection import contracts as detector_contracts
from hogflow.models import Detection, Frame


def test_exactly_one_detector_protocol_is_public() -> None:
    public_classes = [
        value
        for name, value in vars(detector_contracts).items()
        if inspect.isclass(value) and value.__module__ == detector_contracts.__name__
    ]

    assert public_classes == [Detector]
    assert getattr(Detector, "_is_protocol", False) is True
    assert detector_contracts.__all__ == ["Detector"]


def test_detector_protocol_uses_only_shared_contract_models() -> None:
    hints = get_type_hints(Detector.predict)

    assert hints == {"frame": Frame, "return": Sequence[Detection]}


def test_detector_public_api_is_documented_and_typed() -> None:
    assert inspect.getdoc(Detector)
    assert inspect.getdoc(Detector.predict)
    assert inspect.signature(Detector.predict).return_annotation != inspect.Signature.empty
