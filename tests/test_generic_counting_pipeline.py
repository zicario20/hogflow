from collections.abc import Sequence

import pytest

from hogflow.counting import CrossingDirection, DirectionalLineCounter, Line, Point
from hogflow.models import BoundingBox, Detection, Frame, Track
from hogflow.pipeline import GenericCountingPipeline


def _frame(index: int) -> Frame:
    return Frame(index, 20, 20, bytes(20 * 20 * 3), index / 10.0)


def _track(tracker_id: int, x: float, bottom_y: float) -> Track:
    detection = Detection(
        BoundingBox(x - 1, bottom_y - 2, x + 1, bottom_y),
        0.9,
        0,
        "person",
    )
    return Track(tracker_id, detection)


class _FakeSource:
    def __init__(self, frame_count: int) -> None:
        self.frames = [_frame(index) for index in range(frame_count)]
        self.closed = False
        self.read_calls = 0

    def read(self) -> Frame | None:
        self.read_calls += 1
        if not self.frames:
            return None
        return self.frames.pop(0)

    def close(self) -> None:
        self.closed = True


class _FailingSource(_FakeSource):
    def read(self) -> Frame | None:
        raise RuntimeError("source failure")


class _FakeDetector:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[int] = []

    def predict(self, frame: Frame) -> tuple[Detection, ...]:
        self.calls.append(frame.frame_index)
        if self.fail:
            raise RuntimeError("detector failure")
        return ()


class _FakeTracker:
    def __init__(self, schedule: dict[int, Sequence[Track]]) -> None:
        self.schedule = schedule
        self.calls: list[tuple[int, tuple[Detection, ...]]] = []

    def update(
        self,
        frame: Frame,
        detections: Sequence[Detection],
    ) -> tuple[Track, ...]:
        detection_tuple = tuple(detections)
        self.calls.append((frame.frame_index, detection_tuple))
        return tuple(self.schedule.get(frame.frame_index, ()))


def _pipeline(
    schedule: dict[int, Sequence[Track]],
    *,
    frame_count: int | None = None,
    epsilon: float = 0.0,
    ttl: int = 300,
) -> tuple[GenericCountingPipeline, _FakeSource, _FakeDetector, _FakeTracker]:
    if frame_count is None:
        frame_count = max(schedule, default=-1) + 1
    source = _FakeSource(frame_count)
    detector = _FakeDetector()
    tracker = _FakeTracker(schedule)
    counter = DirectionalLineCounter(
        Line(Point(0, 10), Point(10, 10)),
        CrossingDirection.NEGATIVE_TO_POSITIVE,
        epsilon=epsilon,
    )
    pipeline = GenericCountingPipeline(
        source,
        detector,
        tracker,
        counter,
        tracker_state_ttl_frames=ttl,
    )
    return pipeline, source, detector, tracker


def test_one_valid_positive_crossing() -> None:
    pipeline, _source, _detector, _tracker = _pipeline(
        {0: [_track(1, 5, 7)], 1: [_track(1, 5, 13)]}
    )

    summary = pipeline.run()

    assert summary.processed_frames == 2
    assert summary.crossing_event_count == 1
    assert summary.positive_count == 1


def test_reverse_crossing_is_forwarded_without_counting() -> None:
    pipeline, _source, _detector, _tracker = _pipeline(
        {0: [_track(1, 5, 13)], 1: [_track(1, 5, 7)]}
    )
    events = []

    summary = pipeline.run(on_event=lambda event, _frame, _count: events.append(event))

    assert summary.positive_count == 0
    assert len(events) == 1
    assert events[0].direction is CrossingDirection.POSITIVE_TO_NEGATIVE
    assert events[0].counted is False


def test_duplicate_positive_tracker_counts_only_once() -> None:
    pipeline, _source, _detector, _tracker = _pipeline(
        {
            0: [_track(1, 5, 7)],
            1: [_track(1, 5, 13)],
            2: [_track(1, 5, 7)],
            3: [_track(1, 5, 13)],
        }
    )
    counted_flags: list[bool] = []

    summary = pipeline.run(
        on_event=lambda event, _frame, _count: counted_flags.append(event.counted)
    )

    assert summary.positive_count == 1
    assert counted_flags == [True, False, False]


def test_two_trackers_can_each_count_once() -> None:
    pipeline, _source, _detector, _tracker = _pipeline(
        {
            0: [_track(1, 3, 7), _track(2, 7, 7)],
            1: [_track(1, 3, 13), _track(2, 7, 13)],
        }
    )

    assert pipeline.run().positive_count == 2


def test_crossing_outside_finite_segment_is_ignored() -> None:
    pipeline, _source, _detector, _tracker = _pipeline(
        {0: [_track(1, 15, 7)], 1: [_track(1, 15, 13)]}
    )

    summary = pipeline.run()

    assert summary.crossing_event_count == 0
    assert summary.positive_count == 0


def test_near_line_transition_preserves_counter_behavior() -> None:
    pipeline, _source, _detector, _tracker = _pipeline(
        {
            0: [_track(1, 5, 7)],
            1: [_track(1, 5, 10)],
            2: [_track(1, 5, 13)],
        },
        epsilon=1.0,
    )

    assert pipeline.run().positive_count == 1


def test_zero_detections_are_passed_to_tracker() -> None:
    pipeline, _source, detector, tracker = _pipeline({}, frame_count=1)

    summary = pipeline.run()

    assert summary.processed_frames == 1
    assert detector.calls == [0]
    assert tracker.calls == [(0, ())]


def test_zero_tracks_produce_no_events() -> None:
    pipeline, _source, _detector, _tracker = _pipeline({}, frame_count=2)

    summary = pipeline.run()

    assert summary.crossing_event_count == 0
    assert summary.positive_count == 0


def test_normal_source_end_returns_summary() -> None:
    pipeline, source, _detector, _tracker = _pipeline({}, frame_count=0)

    summary = pipeline.run()

    assert summary.processed_frames == 0
    assert source.read_calls == 1


def test_max_frames_stops_without_reading_an_extra_frame() -> None:
    pipeline, source, detector, _tracker = _pipeline({}, frame_count=5)

    summary = pipeline.run(max_frames=2)

    assert summary.processed_frames == 2
    assert source.read_calls == 2
    assert detector.calls == [0, 1]


def test_source_is_closed_after_success() -> None:
    pipeline, source, _detector, _tracker = _pipeline({}, frame_count=1)

    pipeline.run()

    assert source.closed is True


def test_source_is_closed_after_processing_failure() -> None:
    source = _FakeSource(1)
    detector = _FakeDetector(fail=True)
    counter = DirectionalLineCounter(
        Line(Point(0, 10), Point(10, 10)),
        CrossingDirection.NEGATIVE_TO_POSITIVE,
    )
    pipeline = GenericCountingPipeline(source, detector, _FakeTracker({}), counter)

    with pytest.raises(RuntimeError, match="detector failure"):
        pipeline.run()

    assert source.closed is True


def test_source_is_closed_when_read_fails() -> None:
    source = _FailingSource(0)
    counter = DirectionalLineCounter(
        Line(Point(0, 10), Point(10, 10)),
        CrossingDirection.NEGATIVE_TO_POSITIVE,
    )
    pipeline = GenericCountingPipeline(source, _FakeDetector(), _FakeTracker({}), counter)

    with pytest.raises(RuntimeError, match="source failure"):
        pipeline.run()

    assert source.closed is True


def test_frame_and_event_callbacks_receive_results() -> None:
    pipeline, _source, _detector, _tracker = _pipeline(
        {0: [_track(1, 5, 7)], 1: [_track(1, 5, 13)]}
    )
    frame_results = []
    event_results = []

    pipeline.run(
        on_frame=lambda result: frame_results.append(result),
        on_event=lambda event, frame, count: event_results.append((event, frame, count)),
    )

    assert len(frame_results) == 2
    assert frame_results[-1].current_count == 1
    assert len(frame_results[-1].crossing_events) == 1
    assert len(event_results) == 1
    assert event_results[0][1].frame_index == 1
    assert event_results[0][2] == 1


def test_frame_callback_can_stop_processing() -> None:
    pipeline, source, _detector, _tracker = _pipeline({}, frame_count=5)

    summary = pipeline.run(on_frame=lambda _result: False)

    assert summary.processed_frames == 1
    assert source.closed is True


def test_ttl_forgets_only_transient_state_and_preserves_counted_id() -> None:
    pipeline, _source, _detector, _tracker = _pipeline(
        {
            0: [_track(1, 5, 7)],
            1: [_track(1, 5, 13)],
            4: [_track(1, 5, 7)],
            5: [_track(1, 5, 13)],
        },
        frame_count=6,
        ttl=1,
    )
    flags: list[bool] = []

    summary = pipeline.run(on_event=lambda event, _frame, _count: flags.append(event.counted))

    assert summary.positive_count == 1
    assert flags == [True, False]
    assert pipeline.counter.counted_tracker_ids == frozenset({1})
