from hogflow.counting.line_crossing import (
    CrossingDirection,
    DirectionalLineCounter,
    Line,
    Point,
)


def horizontal_counter(*, epsilon: float = 0.1) -> DirectionalLineCounter:
    return DirectionalLineCounter(
        line=Line(start=Point(0.0, 0.0), end=Point(10.0, 0.0)),
        positive_direction=CrossingDirection.NEGATIVE_TO_POSITIVE,
        epsilon=epsilon,
    )


def test_tracker_stays_on_one_side_without_crossing() -> None:
    counter = horizontal_counter()

    events = [
        counter.update(1, Point(1.0, -5.0)),
        counter.update(1, Point(4.0, -4.0)),
        counter.update(1, Point(8.0, -2.0)),
    ]

    assert events == [None, None, None]
    assert counter.count == 0


def test_positive_crossing_counts_once() -> None:
    counter = horizontal_counter()

    assert counter.update(17, Point(5.0, -2.0)) is None
    event = counter.update(17, Point(5.0, 2.0))

    assert event is not None
    assert event.direction is CrossingDirection.NEGATIVE_TO_POSITIVE
    assert event.counted is True
    assert event.previous_point == Point(5.0, -2.0)
    assert event.current_point == Point(5.0, 2.0)
    assert counter.count == 1


def test_reverse_crossing_is_observable_but_not_counted() -> None:
    counter = horizontal_counter()

    assert counter.update(2, Point(5.0, 3.0)) is None
    event = counter.update(2, Point(5.0, -3.0))

    assert event is not None
    assert event.direction is CrossingDirection.POSITIVE_TO_NEGATIVE
    assert event.counted is False
    assert counter.count == 0


def test_touch_line_and_return_does_not_cross() -> None:
    counter = horizontal_counter(epsilon=0.5)

    events = [
        counter.update(3, Point(5.0, -3.0)),
        counter.update(3, Point(5.0, 0.0)),
        counter.update(3, Point(5.0, -2.0)),
    ]

    assert events == [None, None, None]
    assert counter.count == 0


def test_crossing_through_near_line_state_counts_once() -> None:
    counter = horizontal_counter(epsilon=0.5)

    assert counter.update(4, Point(5.0, -3.0)) is None
    assert counter.update(4, Point(5.0, 0.1)) is None
    event = counter.update(4, Point(5.0, 3.0))

    assert event is not None
    assert event.counted is True
    assert len(counter.events) == 1
    assert counter.count == 1


def test_repeated_positive_crossing_by_same_tracker_counts_only_first() -> None:
    counter = horizontal_counter()

    assert counter.update(5, Point(5.0, -3.0)) is None
    first_positive = counter.update(5, Point(5.0, 3.0))
    reverse = counter.update(5, Point(5.0, -3.0))
    second_positive = counter.update(5, Point(5.0, 3.0))

    assert first_positive is not None and first_positive.counted is True
    assert reverse is not None
    assert reverse.direction is CrossingDirection.POSITIVE_TO_NEGATIVE
    assert reverse.counted is False
    assert second_positive is not None
    assert second_positive.direction is CrossingDirection.NEGATIVE_TO_POSITIVE
    assert second_positive.counted is False
    assert counter.count == 1


def test_two_unique_trackers_cross_and_count_independently() -> None:
    counter = horizontal_counter()

    for tracker_id in (11, 12):
        assert counter.update(tracker_id, Point(5.0, -2.0)) is None
        event = counter.update(tracker_id, Point(5.0, 2.0))
        assert event is not None and event.counted is True

    assert counter.count == 2
    assert counter.counted_tracker_ids == frozenset({11, 12})


def test_same_side_observations_after_crossing_do_not_repeat_events() -> None:
    counter = horizontal_counter()

    counter.update(20, Point(5.0, -2.0))
    first_event = counter.update(20, Point(5.0, 2.0))
    later_events = [
        counter.update(20, Point(5.0, 2.5)),
        counter.update(20, Point(5.0, 4.0)),
        counter.update(20, Point(8.0, 6.0)),
    ]

    assert first_event is not None
    assert later_events == [None, None, None]
    assert len(counter.events) == 1
    assert counter.count == 1


def test_arbitrary_diagonal_line_supports_crossing() -> None:
    line = Line(start=Point(0.0, 0.0), end=Point(10.0, 10.0))
    counter = DirectionalLineCounter(
        line=line,
        positive_direction=CrossingDirection.NEGATIVE_TO_POSITIVE,
        epsilon=0.1,
    )

    negative_point = Point(5.0, 0.0)
    positive_point = Point(5.0, 10.0)
    assert line.side_value(negative_point) < 0
    assert line.side_value(positive_point) > 0
    assert counter.update(30, negative_point) is None

    event = counter.update(30, positive_point)

    assert event is not None and event.counted is True
    assert counter.count == 1


def test_epsilon_suppresses_noise_until_meaningful_side_change() -> None:
    counter = horizontal_counter(epsilon=0.5)

    events = [
        counter.update(40, Point(5.0, -1.0)),
        counter.update(40, Point(5.0, -0.1)),
        counter.update(40, Point(5.0, 0.1)),
        counter.update(40, Point(5.0, 0.49)),
        counter.update(40, Point(5.0, 1.0)),
        counter.update(40, Point(5.0, 1.1)),
        counter.update(40, Point(5.0, 0.05)),
        counter.update(40, Point(5.0, 1.2)),
    ]

    crossing_events = [event for event in events if event is not None]
    assert len(crossing_events) == 1
    assert crossing_events[0].counted is True
    assert counter.count == 1


def test_reset_clears_count_ids_events_and_tracker_state() -> None:
    counter = horizontal_counter()

    for tracker_id in (50, 51):
        counter.update(tracker_id, Point(5.0, -2.0))
        counter.update(tracker_id, Point(5.0, 2.0))

    assert counter.count == 2
    counter.reset()

    assert counter.count == 0
    assert counter.counted_tracker_ids == frozenset()
    assert counter.events == ()
    assert counter.update(50, Point(5.0, -2.0)) is None
    event = counter.update(50, Point(5.0, 2.0))
    assert event is not None and event.counted is True
    assert counter.count == 1


def test_tracker_histories_do_not_interfere() -> None:
    counter = horizontal_counter(epsilon=0.5)

    assert counter.update(60, Point(2.0, -3.0)) is None
    assert counter.update(61, Point(8.0, -3.0)) is None
    tracker_two_event = counter.update(61, Point(8.0, 3.0))
    assert counter.update(60, Point(2.0, 0.0)) is None
    assert counter.update(60, Point(2.0, -2.0)) is None

    assert tracker_two_event is not None and tracker_two_event.counted is True
    assert counter.count == 1
    assert counter.counted_tracker_ids == frozenset({61})


def test_forgetting_inactive_tracker_state_keeps_unique_count_guard() -> None:
    counter = horizontal_counter()

    counter.update(70, Point(5.0, -2.0))
    counter.update(70, Point(5.0, 2.0))
    counter.forget_tracker(70)
    assert counter.update(70, Point(5.0, -2.0)) is None
    repeated_positive = counter.update(70, Point(5.0, 2.0))

    assert repeated_positive is not None
    assert repeated_positive.counted is False
    assert counter.count == 1
