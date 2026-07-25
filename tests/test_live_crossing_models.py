from dataclasses import FrozenInstanceError
from datetime import datetime

import pytest

from hogflow.core import ConfigurationError, InputDataError
from hogflow.counting import (
    LineSide,
    LiveCrossingConfiguration,
    LiveCrossingDirection,
    LiveCrossingEvent,
    NormalizedLine,
    NormalizedPoint,
    TrackAnchor,
)


@pytest.mark.parametrize(
    "x,y",
    (
        (float("nan"), 0.5),
        (0.5, float("inf")),
        (-0.1, 0.5),
        (0.5, 1.1),
        (True, 0.5),
    ),
)
def test_normalized_point_rejects_invalid_coordinates(x: object, y: object) -> None:
    with pytest.raises(InputDataError):
        NormalizedPoint(x, y)  # type: ignore[arg-type]


def test_normalized_point_and_configuration_are_immutable() -> None:
    point = NormalizedPoint(0.25, 0.75)
    configuration = LiveCrossingConfiguration(
        enabled=True,
        line=NormalizedLine(NormalizedPoint(0, 0.5), NormalizedPoint(1, 0.5)),
    )

    with pytest.raises(FrozenInstanceError):
        point.x = 0.5  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        configuration.epsilon = 0.1  # type: ignore[misc]


def test_normalized_line_rejects_zero_length() -> None:
    point = NormalizedPoint(0.5, 0.5)

    with pytest.raises(InputDataError, match="different"):
        NormalizedLine(point, point)


@pytest.mark.parametrize("epsilon", (float("nan"), float("inf"), -0.1, 1.1, True))
def test_crossing_configuration_rejects_invalid_epsilon(epsilon: object) -> None:
    with pytest.raises(ConfigurationError):
        LiveCrossingConfiguration(epsilon=epsilon)  # type: ignore[arg-type]


def test_enabled_configuration_requires_line_and_valid_retention() -> None:
    with pytest.raises(ConfigurationError, match="requires"):
        LiveCrossingConfiguration(enabled=True)
    with pytest.raises(ConfigurationError, match="retention"):
        LiveCrossingConfiguration(absent_track_retention_updates=-1)


def test_configuration_fingerprint_is_stable_and_sensitive() -> None:
    line = NormalizedLine(NormalizedPoint(0.2, 0.5), NormalizedPoint(0.8, 0.5))
    first = LiveCrossingConfiguration(enabled=True, line=line)
    same = LiveCrossingConfiguration(enabled=True, line=line)
    changed = LiveCrossingConfiguration(enabled=True, line=line, anchor=TrackAnchor.CENTER)

    assert first.fingerprint == same.fingerprint
    assert first.fingerprint != changed.fingerprint
    assert len(first.fingerprint) == 64


@pytest.mark.parametrize(
    "line,positive,negative,on_line",
    (
        (
            NormalizedLine(NormalizedPoint(0, 0.5), NormalizedPoint(1, 0.5)),
            NormalizedPoint(0.5, 0.8),
            NormalizedPoint(0.5, 0.2),
            NormalizedPoint(0.5, 0.5),
        ),
        (
            NormalizedLine(NormalizedPoint(0.5, 0), NormalizedPoint(0.5, 1)),
            NormalizedPoint(0.2, 0.5),
            NormalizedPoint(0.8, 0.5),
            NormalizedPoint(0.5, 0.5),
        ),
        (
            NormalizedLine(NormalizedPoint(0, 0), NormalizedPoint(1, 1)),
            NormalizedPoint(0.2, 0.8),
            NormalizedPoint(0.8, 0.2),
            NormalizedPoint(0.5, 0.5),
        ),
    ),
)
def test_geometry_classifies_horizontal_vertical_and_diagonal_lines(
    line: NormalizedLine,
    positive: NormalizedPoint,
    negative: NormalizedPoint,
    on_line: NormalizedPoint,
) -> None:
    assert line.classify(positive, 1e-6) is LineSide.POSITIVE
    assert line.classify(negative, 1e-6) is LineSide.NEGATIVE
    assert line.classify(on_line, 1e-6) is LineSide.ON_LINE


def test_epsilon_and_endpoint_reversal_are_predictable() -> None:
    line = NormalizedLine(NormalizedPoint(0, 0.5), NormalizedPoint(1, 0.5))
    reversed_line = NormalizedLine(line.end, line.start)
    point = NormalizedPoint(0.5, 0.5005)

    assert line.classify(point, 0.001) is LineSide.ON_LINE
    assert line.classify(point, 0.0001) is LineSide.POSITIVE
    assert reversed_line.classify(point, 0.0001) is LineSide.NEGATIVE


def test_finite_segment_intersection_rejects_invisible_extension() -> None:
    line = NormalizedLine(NormalizedPoint(0.2, 0.5), NormalizedPoint(0.8, 0.5))

    assert line.intersects_movement_segment(NormalizedPoint(0.5, 0.2), NormalizedPoint(0.5, 0.8))
    assert not line.intersects_movement_segment(
        NormalizedPoint(0.95, 0.2), NormalizedPoint(0.95, 0.8)
    )
    assert line.intersects_movement_segment(NormalizedPoint(0.2, 0.2), NormalizedPoint(0.2, 0.8))


def test_event_requires_timezone_and_matching_geometric_direction() -> None:
    arguments = {
        "source_id": "camera",
        "tracker_lifecycle_id": "crossing-lifecycle-1",
        "tracker_id": 1,
        "frame_sequence": 2,
        "previous_frame_sequence": 1,
        "captured_at": datetime(2026, 7, 25),
        "direction": LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
        "previous_side": LineSide.NEGATIVE,
        "current_side": LineSide.POSITIVE,
        "previous_point": NormalizedPoint(0.5, 0.2),
        "representative_point": NormalizedPoint(0.5, 0.8),
        "line_id": "line-123",
        "configuration_fingerprint": "a" * 64,
    }

    with pytest.raises(InputDataError, match="timezone"):
        LiveCrossingEvent(**arguments)  # type: ignore[arg-type]

    arguments["captured_at"] = datetime.now().astimezone()
    arguments["direction"] = LiveCrossingDirection.POSITIVE_TO_NEGATIVE
    with pytest.raises(InputDataError, match="direction"):
        LiveCrossingEvent(**arguments)  # type: ignore[arg-type]
