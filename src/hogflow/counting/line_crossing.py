"""Detector-independent directional line-crossing logic.

The side of a point is derived from the signed 2D cross product for the directed
line ``start -> end``. A positive value is on the mathematically positive side
of that directed line, and a negative value is on the opposite side. Reversing
the line endpoints reverses this sign convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import hypot, isfinite

_SEGMENT_INTERSECTION_TOLERANCE = 1e-9


@dataclass(frozen=True, slots=True)
class Point:
    """A finite two-dimensional point."""

    x: float
    y: float

    def __post_init__(self) -> None:
        if not isfinite(self.x) or not isfinite(self.y):
            raise ValueError("Point coordinates must be finite numbers.")


@dataclass(frozen=True, slots=True)
class Line:
    """A directed line segment defined by distinct start and end points."""

    start: Point
    end: Point

    def __post_init__(self) -> None:
        if self.start == self.end:
            raise ValueError("Line start and end points must be different.")

    def side_value(self, point: Point) -> float:
        """Return the signed orientation cross product for ``point``.

        Positive and negative results identify opposite sides of the directed
        line. The magnitude scales with line length.
        """

        line_x = self.end.x - self.start.x
        line_y = self.end.y - self.start.y
        point_x = point.x - self.start.x
        point_y = point.y - self.start.y
        return line_x * point_y - line_y * point_x

    def signed_distance(self, point: Point) -> float:
        """Return signed perpendicular distance from the supporting infinite line."""

        length = hypot(self.end.x - self.start.x, self.end.y - self.start.y)
        return self.side_value(point) / length

    def intersects_movement_segment(self, previous: Point, current: Point) -> bool:
        """Return whether a movement segment intersects this finite segment.

        Intersections at either endpoint are included within a small numerical
        tolerance. Parallel and collinear segments return ``False``; the
        counter's meaningful-side transition rule excludes sliding movement.
        """

        movement_x = current.x - previous.x
        movement_y = current.y - previous.y
        counting_x = self.end.x - self.start.x
        counting_y = self.end.y - self.start.y

        denominator = movement_x * counting_y - movement_y * counting_x
        denominator_scale = max(
            hypot(movement_x, movement_y) * hypot(counting_x, counting_y),
            1.0,
        )
        if abs(denominator) <= _SEGMENT_INTERSECTION_TOLERANCE * denominator_scale:
            return False

        offset_x = self.start.x - previous.x
        offset_y = self.start.y - previous.y
        movement_parameter = (offset_x * counting_y - offset_y * counting_x) / denominator
        counting_parameter = (offset_x * movement_y - offset_y * movement_x) / denominator
        tolerance = _SEGMENT_INTERSECTION_TOLERANCE
        return (
            -tolerance <= movement_parameter <= 1.0 + tolerance
            and -tolerance <= counting_parameter <= 1.0 + tolerance
        )


class CrossingDirection(str, Enum):
    """A meaningful transition between opposite sides of a directed line."""

    NEGATIVE_TO_POSITIVE = "negative_to_positive"
    POSITIVE_TO_NEGATIVE = "positive_to_negative"


@dataclass(frozen=True, slots=True)
class CrossingEvent:
    """One observed side-to-side crossing for a tracker."""

    tracker_id: int
    direction: CrossingDirection
    counted: bool
    previous_point: Point
    current_point: Point


class _Side(Enum):
    NEGATIVE = -1
    NEAR_LINE = 0
    POSITIVE = 1


@dataclass(frozen=True, slots=True)
class _TrackerState:
    last_meaningful_side: _Side
    last_meaningful_point: Point


class DirectionalLineCounter:
    """Count unique tracker IDs crossing a finite segment in one direction.

    ``epsilon`` is a perpendicular-distance tolerance in the same coordinate
    units as the points. Observations within that distance of the segment's
    supporting infinite line are treated as near-line observations and do not
    replace the last meaningful side. This allows
    ``negative -> near line -> positive`` to create one event when the implied
    movement intersects the finite segment, while
    ``negative -> near line -> negative`` creates none.
    """

    def __init__(
        self,
        line: Line,
        positive_direction: CrossingDirection,
        *,
        epsilon: float = 1.0,
    ) -> None:
        if not isinstance(positive_direction, CrossingDirection):
            raise TypeError("positive_direction must be a CrossingDirection.")
        if not isfinite(epsilon) or epsilon < 0:
            raise ValueError("epsilon must be a finite, non-negative number.")

        self.line = line
        self.positive_direction = positive_direction
        self.epsilon = epsilon
        self._counted_tracker_ids: set[int] = set()
        self._tracker_states: dict[int, _TrackerState] = {}
        self._events: list[CrossingEvent] = []

    @property
    def count(self) -> int:
        """Return the number of unique eligible positive tracker crossings."""

        return len(self._counted_tracker_ids)

    @property
    def counted_tracker_ids(self) -> frozenset[int]:
        """Return a read-only snapshot of tracker IDs that contributed to count."""

        return frozenset(self._counted_tracker_ids)

    @property
    def events(self) -> tuple[CrossingEvent, ...]:
        """Return an immutable snapshot of crossing events observed so far."""

        return tuple(self._events)

    def update(self, tracker_id: int, point: Point) -> CrossingEvent | None:
        """Process one tracker observation and return a crossing event if present.

        The first meaningful observation establishes tracker state. A subsequent
        observation on the opposite meaningful side creates an event only when
        the movement between meaningful points intersects the finite counting
        segment. Near-line observations preserve the last meaningful side and
        point.
        """

        if not isinstance(tracker_id, int) or isinstance(tracker_id, bool):
            raise TypeError("tracker_id must be an integer.")

        current_side = self._classify_side(point)
        if current_side is _Side.NEAR_LINE:
            return None

        previous_state = self._tracker_states.get(tracker_id)
        self._tracker_states[tracker_id] = _TrackerState(current_side, point)

        if previous_state is None or previous_state.last_meaningful_side is current_side:
            return None

        if not self.line.intersects_movement_segment(
            previous_state.last_meaningful_point,
            point,
        ):
            return None

        direction = self._transition_direction(
            previous_state.last_meaningful_side,
            current_side,
        )
        counted = (
            direction is self.positive_direction and tracker_id not in self._counted_tracker_ids
        )
        if counted:
            self._counted_tracker_ids.add(tracker_id)

        event = CrossingEvent(
            tracker_id=tracker_id,
            direction=direction,
            counted=counted,
            previous_point=previous_state.last_meaningful_point,
            current_point=point,
        )
        self._events.append(event)
        return event

    def forget_tracker(self, tracker_id: int) -> None:
        """Discard only transient side state for an inactive tracker.

        Counted IDs and historical events intentionally remain for the complete
        Phase 1 run, preventing a previously counted ID from counting again.
        """

        self._tracker_states.pop(tracker_id, None)

    def reset(self) -> None:
        """Clear count state, tracker side state, and stored crossing events."""

        self._counted_tracker_ids.clear()
        self._tracker_states.clear()
        self._events.clear()

    def _classify_side(self, point: Point) -> _Side:
        distance = self.line.signed_distance(point)
        if distance > self.epsilon:
            return _Side.POSITIVE
        if distance < -self.epsilon:
            return _Side.NEGATIVE
        return _Side.NEAR_LINE

    @staticmethod
    def _transition_direction(previous: _Side, current: _Side) -> CrossingDirection:
        if previous is _Side.NEGATIVE and current is _Side.POSITIVE:
            return CrossingDirection.NEGATIVE_TO_POSITIVE
        if previous is _Side.POSITIVE and current is _Side.NEGATIVE:
            return CrossingDirection.POSITIVE_TO_NEGATIVE
        raise RuntimeError("Crossing transition requires opposite meaningful sides.")
