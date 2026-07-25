from __future__ import annotations

from datetime import datetime, timezone

import pytest
from _phase6_helpers import (
    clean_pass_replay,
    extension_replay,
    jitter_gap_replay,
    reference_candidate_plan,
    three_candidate_plan,
    tracked_object,
    tracking_result,
    vertical_candidate,
)

from hogflow.counting import NormalizedLine, NormalizedPoint, TrackAnchor
from hogflow.evaluation import (
    LineCandidate,
    LineEvaluationPlan,
    LineRankingMethod,
    TrackingReplay,
    VirtualLinePositionEvaluator,
)
from hogflow.evaluation.line_errors import LineEvaluationExecutionError


class ConstantClock:
    def __call__(self) -> float:
        return 100.0


def _evaluator() -> VirtualLinePositionEvaluator:
    fixed = datetime(2026, 7, 26, tzinfo=timezone.utc)
    return VirtualLinePositionEvaluator(
        monotonic_clock=ConstantClock(),
        wall_clock=lambda: fixed,
    )


def test_one_candidate_replays_frames_and_emits_event() -> None:
    plan = LineEvaluationPlan(
        plan_id="one",
        candidates=(vertical_candidate("center", 0.5),),
        ranking_method=LineRankingMethod.EVENT_F1,
    )

    report = _evaluator().evaluate(plan, clean_pass_replay())
    result = report.candidate_results[0]

    assert result.tracking_results_processed == 4
    assert result.tracks_observed == 1
    assert result.events_total == 1
    assert result.frames_with_events == 1
    assert result.ground_truth_metrics is not None
    assert result.ground_truth_metrics.f1_score == 1
    assert report.recommended_candidate_id == "center"


def test_candidate_order_does_not_change_results_by_id() -> None:
    candidates = (
        vertical_candidate("left", 0.3),
        vertical_candidate("center", 0.5),
        vertical_candidate("right", 0.7),
    )
    forward = LineEvaluationPlan(
        plan_id="order",
        candidates=candidates,
        ranking_method=LineRankingMethod.EVENT_F1,
    )
    reverse = LineEvaluationPlan(
        plan_id="order",
        candidates=tuple(reversed(candidates)),
        ranking_method=LineRankingMethod.EVENT_F1,
    )

    first = _evaluator().evaluate(forward, clean_pass_replay())
    second = _evaluator().evaluate(reverse, clean_pass_replay())

    assert first.candidate_results == second.candidate_results
    assert first.ranked_candidate_ids == second.ranked_candidate_ids
    assert first.plan.fingerprint == second.plan.fingerprint


def test_same_replay_is_deterministic() -> None:
    first = _evaluator().evaluate(three_candidate_plan(), clean_pass_replay())
    second = _evaluator().evaluate(three_candidate_plan(), clean_pass_replay())

    assert first == second
    assert tuple(
        result.deterministic_event_fingerprint for result in first.candidate_results
    ) == tuple(result.deterministic_event_fingerprint for result in second.candidate_results)


def test_reference_candidate_geometries_are_supported() -> None:
    report = _evaluator().evaluate(
        reference_candidate_plan(),
        clean_pass_replay(with_ground_truth=False),
    )

    assert tuple(result.candidate_id for result in report.candidate_results) == (
        "diagonal",
        "horizontal",
        "segment-long",
        "segment-short",
        "vertical-center",
        "vertical-left",
        "vertical-right",
    )
    assert report.recommended_candidate_id is None


def test_short_segment_rejects_extension_while_long_segment_emits() -> None:
    plan = LineEvaluationPlan(
        plan_id="segments",
        candidates=(
            vertical_candidate("short", 0.5, y_start=0.4, y_end=0.6),
            vertical_candidate("long", 0.5, y_start=0.1, y_end=0.9),
        ),
    )

    results = {
        result.candidate_id: result
        for result in _evaluator().evaluate(plan, extension_replay()).candidate_results
    }

    assert results["short"].events_total == 0
    assert results["long"].events_total == 1


def test_line_outside_trajectory_and_reversed_direction() -> None:
    normal = vertical_candidate("normal", 0.5)
    outside = vertical_candidate("outside", 0.9)
    reversed_line = LineCandidate(
        candidate_id="reversed",
        line=NormalizedLine(normal.line.end, normal.line.start),
        epsilon=normal.epsilon,
    )
    report = _evaluator().evaluate(
        LineEvaluationPlan(
            plan_id="direction",
            candidates=(normal, outside, reversed_line),
        ),
        clean_pass_replay(with_ground_truth=False),
    )
    results = {result.candidate_id: result for result in report.candidate_results}

    assert results["outside"].events_total == 0
    assert results["normal"].positive_to_negative_events == 1
    assert results["reversed"].negative_to_positive_events == 1


def test_anchor_and_epsilon_change_candidate_behavior() -> None:
    replay = TrackingReplay(
        source_id="synthetic-source",
        replay_id="anchor-epsilon",
        tracker_lifecycle_id="lifecycle",
        tracking_results=(
            tracking_result(
                0,
                (
                    tracked_object(1, 50, 40, box_height=20),
                    tracked_object(2, 30, 80, box_height=20),
                ),
            ),
            tracking_result(
                1,
                (
                    tracked_object(1, 50, 60, box_height=20),
                    tracked_object(2, 70, 80, box_height=20),
                ),
            ),
        ),
        evidence_level=clean_pass_replay().evidence_level,
        provenance="synthetic",
    )
    horizontal = NormalizedLine(NormalizedPoint(0.1, 0.55), NormalizedPoint(0.9, 0.55))
    plan = LineEvaluationPlan(
        plan_id="anchor-epsilon",
        candidates=(
            LineCandidate(
                candidate_id="bottom",
                line=horizontal,
                anchor=TrackAnchor.BOTTOM_CENTER,
                epsilon=0.001,
            ),
            LineCandidate(
                candidate_id="center",
                line=horizontal,
                anchor=TrackAnchor.CENTER,
                epsilon=0.001,
            ),
            vertical_candidate("wide-epsilon", 0.5, epsilon=0.3),
            vertical_candidate("narrow-epsilon", 0.5, epsilon=0.001),
        ),
    )

    results = {
        result.candidate_id: result
        for result in _evaluator().evaluate(plan, replay).candidate_results
    }

    assert results["bottom"].events_total == 1
    assert results["center"].events_total == 0
    assert results["wide-epsilon"].events_total == 0
    assert results["narrow-epsilon"].events_total == 1


def test_gap_and_near_endpoint_diagnostics() -> None:
    plan = LineEvaluationPlan(
        plan_id="gap-diagnostics",
        candidates=(vertical_candidate("short-edge", 0.5, y_start=0.4, y_end=0.6),),
        matching_window_frames=1,
        near_endpoint_distance=0.06,
        large_gap_threshold=5,
    )

    result = _evaluator().evaluate(plan, jitter_gap_replay()).candidate_results[0]

    assert result.gap_count == 2
    assert result.maximum_gap == 6
    assert result.events_after_gaps >= 1
    assert result.events_after_large_gaps >= 1
    assert result.events_near_endpoints >= 1
    assert result.event_after_gap_ratio > 0


@pytest.mark.parametrize(
    "method",
    (
        LineRankingMethod.EVENT_F1,
        LineRankingMethod.ABSOLUTE_EVENT_COUNT_ERROR,
        LineRankingMethod.MEAN_FRAME_OFFSET,
    ),
)
def test_ground_truth_ranking_is_explicit_and_stable(method: LineRankingMethod) -> None:
    report = _evaluator().evaluate(
        three_candidate_plan(ranking=method),
        clean_pass_replay(),
    )

    assert report.ranked_candidate_ids[0] == "line-center"
    assert report.recommended_candidate_id == "line-center"


def test_final_ranking_tie_break_uses_candidate_id() -> None:
    same_line = vertical_candidate("line-b", 0.5)
    other_id = LineCandidate(
        candidate_id="line-a",
        line=same_line.line,
        anchor=same_line.anchor,
        epsilon=same_line.epsilon,
        absent_track_retention_updates=same_line.absent_track_retention_updates,
        tags=same_line.tags,
    )
    report = _evaluator().evaluate(
        LineEvaluationPlan(
            plan_id="tie",
            candidates=(same_line, other_id),
            ranking_method=LineRankingMethod.EVENT_F1,
        ),
        clean_pass_replay(),
    )

    assert report.ranked_candidate_ids == ("line-a", "line-b")


def test_no_ground_truth_or_disabled_ranking_makes_no_recommendation() -> None:
    no_ground_truth = _evaluator().evaluate(
        three_candidate_plan(ranking=LineRankingMethod.EVENT_F1),
        clean_pass_replay(with_ground_truth=False),
    )
    disabled = _evaluator().evaluate(
        three_candidate_plan(ranking=LineRankingMethod.NO_AUTOMATIC_RECOMMENDATION),
        clean_pass_replay(),
    )

    assert no_ground_truth.ranked_candidate_ids == ()
    assert no_ground_truth.recommended_candidate_id is None
    assert "No recommendation" in no_ground_truth.recommendation_explanation
    assert disabled.recommended_candidate_id is None


def test_evaluation_telemetry_is_bounded_and_consistent() -> None:
    evaluator = _evaluator()
    report = evaluator.evaluate(three_candidate_plan(), clean_pass_replay())

    assert report.statistics == evaluator.statistics()
    assert report.statistics.candidates_requested == 3
    assert report.statistics.candidates_completed == 3
    assert report.statistics.frames_replayed == 4
    assert report.statistics.total_crossing_updates == 12
    assert report.statistics.failures == 0
    assert not report.statistics.report_written


def test_each_candidate_detector_closes_on_success_and_error() -> None:
    from hogflow.counting import VirtualLineCrossingDetector

    instances: list[VirtualLineCrossingDetector] = []

    class RecordingDetector(VirtualLineCrossingDetector):
        def close(self) -> None:
            super().close()
            self.was_closed = True

    def factory(configuration, **kwargs):
        detector = RecordingDetector(configuration, **kwargs)
        detector.was_closed = False
        instances.append(detector)
        return detector

    evaluator = VirtualLinePositionEvaluator(
        detector_factory=factory,
        monotonic_clock=ConstantClock(),
        wall_clock=lambda: datetime(2026, 7, 26, tzinfo=timezone.utc),
    )
    evaluator.evaluate(three_candidate_plan(), clean_pass_replay())
    assert all(instance.was_closed for instance in instances)

    class FailingDetector(RecordingDetector):
        def update(self, tracking):
            raise RuntimeError("synthetic internal failure")

    failed_instances: list[FailingDetector] = []

    def failing_factory(configuration, **kwargs):
        detector = FailingDetector(configuration, **kwargs)
        detector.was_closed = False
        failed_instances.append(detector)
        return detector

    failed = VirtualLinePositionEvaluator(
        detector_factory=failing_factory,
        monotonic_clock=ConstantClock(),
        wall_clock=lambda: datetime(2026, 7, 26, tzinfo=timezone.utc),
    )
    with pytest.raises(LineEvaluationExecutionError, match="could not be evaluated"):
        failed.evaluate(three_candidate_plan(), clean_pass_replay())
    assert failed_instances[0].was_closed
    assert failed.statistics().failures == 1
