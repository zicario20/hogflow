from dataclasses import FrozenInstanceError, fields
from math import nan

import pytest

from hogflow.core import InputDataError
from hogflow.models import BoundingBox, Detection, Frame, Track


def sample_frame() -> Frame:
    return Frame(
        frame_index=7,
        width=2,
        height=1,
        pixels=bytes((255, 0, 0, 0, 255, 0)),
        timestamp_seconds=0.25,
    )


def sample_detection() -> Detection:
    return Detection(
        bounding_box=BoundingBox(x_min=1.0, y_min=2.0, x_max=5.0, y_max=8.0),
        confidence=0.9,
        class_id=0,
        class_name="person",
    )


def test_shared_model_public_fields_are_explicit() -> None:
    assert tuple(field.name for field in fields(Frame)) == (
        "frame_index",
        "width",
        "height",
        "pixels",
        "timestamp_seconds",
    )
    assert tuple(field.name for field in fields(BoundingBox)) == (
        "x_min",
        "y_min",
        "x_max",
        "y_max",
    )
    assert tuple(field.name for field in fields(Detection)) == (
        "bounding_box",
        "confidence",
        "class_id",
        "class_name",
    )
    assert tuple(field.name for field in fields(Track)) == ("tracker_id", "detection")


@pytest.mark.parametrize(
    "model",
    [
        sample_frame(),
        BoundingBox(x_min=1.0, y_min=2.0, x_max=5.0, y_max=8.0),
        sample_detection(),
        Track(tracker_id=42, detection=sample_detection()),
    ],
)
def test_shared_models_are_frozen(model: object) -> None:
    field_name = fields(model)[0].name

    with pytest.raises(FrozenInstanceError):
        setattr(model, field_name, None)


def test_frame_uses_immutable_packed_rgb_bytes() -> None:
    frame = sample_frame()

    assert frame.pixels == bytes((255, 0, 0, 0, 255, 0))
    assert frame.width == 2
    assert frame.height == 1


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"frame_index": -1}, "index"),
        ({"width": 0}, "width"),
        ({"height": 0}, "height"),
        ({"pixels": b"too short"}, "payload"),
        ({"timestamp_seconds": -0.1}, "timestamp"),
    ],
)
def test_frame_rejects_invalid_contract_data(overrides: dict[str, object], message: str) -> None:
    values: dict[str, object] = {
        "frame_index": 0,
        "width": 1,
        "height": 1,
        "pixels": bytes((0, 0, 0)),
        "timestamp_seconds": 0.0,
    }
    values.update(overrides)

    with pytest.raises(InputDataError, match=message):
        Frame(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "coordinates",
    [
        (0.0, 0.0, 0.0, 1.0),
        (0.0, 0.0, 1.0, 0.0),
        (nan, 0.0, 1.0, 1.0),
    ],
)
def test_bounding_box_requires_finite_positive_area(
    coordinates: tuple[float, float, float, float],
) -> None:
    with pytest.raises(InputDataError):
        BoundingBox(*coordinates)


@pytest.mark.parametrize(
    ("confidence", "class_id", "class_name"),
    [(-0.1, 0, "person"), (1.1, 0, "person"), (0.9, -1, "person"), (0.9, 0, " ")],
)
def test_detection_rejects_invalid_contract_data(
    confidence: float,
    class_id: int,
    class_name: str,
) -> None:
    with pytest.raises(InputDataError):
        Detection(
            bounding_box=BoundingBox(0.0, 0.0, 1.0, 1.0),
            confidence=confidence,
            class_id=class_id,
            class_name=class_name,
        )


def test_track_composes_detection_with_implementation_scoped_identity() -> None:
    detection = sample_detection()
    track = Track(tracker_id=42, detection=detection)

    assert track.tracker_id == 42
    assert track.detection is detection


def test_track_rejects_invalid_identity() -> None:
    with pytest.raises(InputDataError, match="tracker_id"):
        Track(tracker_id=-1, detection=sample_detection())


@pytest.mark.parametrize("public_type", [Frame, BoundingBox, Detection, Track])
def test_shared_models_have_public_documentation_and_type_hints(public_type: type[object]) -> None:
    assert public_type.__doc__
    assert public_type.__annotations__
