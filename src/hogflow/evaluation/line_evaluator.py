"""Serial deterministic evaluator for normalized virtual-line candidates."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from math import hypot, inf
from time import monotonic

from hogflow.counting import (
    LiveCrossingDirection,
    LiveCrossingEvent,
    VirtualLineCrossingDetector,
)
from hogflow.evaluation.line_errors import LineEvaluationExecutionError
from hogflow.evaluation.line_matching import match_crossing_events
from hogflow.evaluation.line_models import (
    CandidateEvaluationResult,
    EvidenceLevel,
    LifecycleEventTotal,
    LineCandidate,
    LineEvaluationErrorCategory,
    LineEvaluationPlan,
    LineEvaluationReport,
    LineEvaluationStats,
    LineRankingMethod,
    TrackingReplay,
)

_HIGH_GAP_EVENT_RATIO = 0.25


def _event_payload(event: LiveCrossingEvent) -> dict[str, object]:
    return {
        "direction": event.direction.value,
        "frame_sequence": event.frame_sequence,
        "previous_frame_sequence": event.previous_frame_sequence,
        "representative_point": {
            "x": event.representative_point.x,
            "y": event.representative_point.y,
        },
        "tracker_id": event.tracker_id,
        "tracker_lifecycle_id": event.tracker_lifecycle_id,
    }


def _event_fingerprint(events: tuple[LiveCrossingEvent, ...]) -> str:
    serialized = json.dumps(
        [_event_payload(event) for event in events],
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _near_endpoint(event: LiveCrossingEvent, candidate: LineCandidate, distance: float) -> bool:
    parameter = candidate.line.movement_intersection_parameter(
        event.previous_point,
        event.representative_point,
    )
    if parameter is None:
        raise LineEvaluationExecutionError(
            "Emitted crossing event does not intersect its candidate segment."
        )
    length = hypot(
        candidate.line.end.x - candidate.line.start.x,
        candidate.line.end.y - candidate.line.start.y,
    )
    nearest_distance = min(parameter, 1.0 - parameter) * length
    return nearest_distance <= distance


def _gap_metrics(replay: TrackingReplay) -> tuple[int, int]:
    missing_frames = tuple(
        current.frame_sequence - previous.frame_sequence - 1
        for previous, current in zip(
            replay.tracking_results,
            replay.tracking_results[1:],
            strict=False,
        )
        if current.frame_sequence - previous.frame_sequence > 1
    )
    return len(missing_frames), max(missing_frames, default=0)


def _candidate_sort_key(
    result: CandidateEvaluationResult,
    ranking_method: LineRankingMethod,
) -> tuple[object, ...]:
    metrics = result.ground_truth_metrics
    if metrics is None:
        return (result.candidate_id,)
    mean_offset = (
        metrics.mean_absolute_frame_offset
        if metrics.mean_absolute_frame_offset is not None
        else inf
    )
    if ranking_method is LineRankingMethod.EVENT_F1:
        return (
            -metrics.f1_score,
            metrics.absolute_event_count_error,
            mean_offset,
            result.candidate_id,
        )
    if ranking_method is LineRankingMethod.ABSOLUTE_EVENT_COUNT_ERROR:
        return (
            metrics.absolute_event_count_error,
            -metrics.f1_score,
            mean_offset,
            result.candidate_id,
        )
    if ranking_method is LineRankingMethod.MEAN_FRAME_OFFSET:
        return (
            mean_offset,
            -metrics.f1_score,
            metrics.absolute_event_count_error,
            result.candidate_id,
        )
    return (result.candidate_id,)


class VirtualLinePositionEvaluator:
    """Replay identical tracking results through isolated crossing detectors.

    Evaluation is serial. Each candidate owns a fresh detector and lifecycle,
    and every detector is closed in a ``finally`` block. Structural or
    candidate execution failures abort the complete report rather than ranking
    incomplete evidence.
    """

    def __init__(
        self,
        *,
        detector_factory: Callable[..., VirtualLineCrossingDetector] = (
            VirtualLineCrossingDetector
        ),
        monotonic_clock: Callable[[], float] = monotonic,
        wall_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._detector_factory = detector_factory
        self._monotonic = monotonic_clock
        self._wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self._last_statistics = LineEvaluationStats(
            candidates_requested=0,
            candidates_completed=0,
            frames_replayed=0,
            total_crossing_updates=0,
            total_events_evaluated=0,
            matching_operations=0,
            evaluation_duration_ms=0,
            report_written=False,
            failures=0,
            last_error_category=LineEvaluationErrorCategory.NONE,
        )

    def evaluate(
        self,
        plan: LineEvaluationPlan,
        replay: TrackingReplay,
    ) -> LineEvaluationReport:
        """Evaluate every canonical candidate against exactly the same replay."""

        if not isinstance(plan, LineEvaluationPlan):
            raise LineEvaluationExecutionError("Evaluation requires a validated line plan.")
        if not isinstance(replay, TrackingReplay):
            raise LineEvaluationExecutionError("Evaluation requires a validated tracking replay.")
        started = float(self._monotonic())
        results: list[CandidateEvaluationResult] = []
        total_updates = 0
        total_events = 0
        matching_operations = 0
        try:
            for candidate in plan.candidates:
                result = self._evaluate_candidate(plan, replay, candidate)
                results.append(result)
                total_updates += result.tracking_results_processed
                total_events += result.events_total
                if result.ground_truth_metrics is not None:
                    matching_operations += result.ground_truth_metrics.matching_operations
        except Exception:
            self._last_statistics = LineEvaluationStats(
                candidates_requested=len(plan.candidates),
                candidates_completed=len(results),
                frames_replayed=len(replay.tracking_results),
                total_crossing_updates=total_updates,
                total_events_evaluated=total_events,
                matching_operations=matching_operations,
                evaluation_duration_ms=max(0.0, float(self._monotonic()) - started) * 1000,
                report_written=False,
                failures=1,
                last_error_category=LineEvaluationErrorCategory.EVALUATION,
            )
            raise

        statistics = LineEvaluationStats(
            candidates_requested=len(plan.candidates),
            candidates_completed=len(results),
            frames_replayed=len(replay.tracking_results),
            total_crossing_updates=total_updates,
            total_events_evaluated=total_events,
            matching_operations=matching_operations,
            evaluation_duration_ms=max(0.0, float(self._monotonic()) - started) * 1000,
            report_written=False,
            failures=0,
            last_error_category=LineEvaluationErrorCategory.NONE,
        )
        self._last_statistics = statistics
        result_tuple = tuple(results)
        ranked_ids, recommendation, explanation = self._rank(plan, replay, result_tuple)
        warnings = self._warnings(replay, result_tuple)
        limitations = tuple(
            sorted(
                {
                    "crossing_events_are_not_unique_animal_counts",
                    "greedy_matching_is_not_global_optimization",
                    "tracking_identity_errors_can_affect_results",
                }
            )
        )
        return LineEvaluationReport(
            plan=plan,
            replay_id=replay.replay_id,
            replay_fingerprint=replay.fingerprint,
            replay_provenance=replay.provenance,
            evidence_level=replay.evidence_level,
            ground_truth_available=bool(replay.ground_truth_events),
            candidate_results=result_tuple,
            ranking_method=plan.ranking_method,
            ranked_candidate_ids=ranked_ids,
            recommended_candidate_id=recommendation,
            recommendation_explanation=explanation,
            warnings=warnings,
            limitations=limitations,
            generated_at=self._wall_clock(),
            statistics=statistics,
        )

    def statistics(self) -> LineEvaluationStats:
        """Return bounded telemetry for the last attempted evaluation."""

        return self._last_statistics

    def _evaluate_candidate(
        self,
        plan: LineEvaluationPlan,
        replay: TrackingReplay,
        candidate: LineCandidate,
    ) -> CandidateEvaluationResult:
        detector = self._detector_factory(
            candidate.to_live_crossing_configuration(),
            monotonic_clock=self._monotonic,
            wall_clock=self._wall_clock,
        )
        events: list[LiveCrossingEvent] = []
        tracks: set[int] = set()
        started = float(self._monotonic())
        try:
            try:
                detector.start(replay.source_id)
                for tracking_result in replay.tracking_results:
                    tracks.update(
                        tracked_object.track.tracker_id
                        for tracked_object in tracking_result.tracked_objects
                    )
                    crossing_result = detector.update(tracking_result)
                    events.extend(crossing_result.events)
            except Exception as exc:
                raise LineEvaluationExecutionError(
                    f"Candidate {candidate.candidate_id!r} could not be evaluated safely."
                ) from exc
        finally:
            try:
                detector.close()
            except Exception as exc:
                raise LineEvaluationExecutionError(
                    f"Candidate {candidate.candidate_id!r} could not close safely."
                ) from exc

        event_tuple = tuple(events)
        gap_count, maximum_gap = _gap_metrics(replay)
        events_after_gaps = sum(
            event.frame_sequence - event.previous_frame_sequence > 1 for event in event_tuple
        )
        events_after_large_gaps = sum(
            event.frame_sequence - event.previous_frame_sequence - 1 >= plan.large_gap_threshold
            for event in event_tuple
        )
        directions = Counter(event.direction for event in event_tuple)
        lifecycle_counts = Counter(event.tracker_lifecycle_id for event in event_tuple)
        ground_truth_metrics = (
            match_crossing_events(
                event_tuple,
                replay.ground_truth_events,
                maximum_frame_offset=plan.matching_window_frames,
                require_direction_match=plan.require_direction_match,
            )
            if replay.ground_truth_events
            else None
        )
        limitations = ["expired_states_not_observable_from_public_crossing_contract"]
        return CandidateEvaluationResult(
            candidate_id=candidate.candidate_id,
            candidate_fingerprint=candidate.fingerprint,
            tracking_results_processed=len(replay.tracking_results),
            tracks_observed=len(tracks),
            events_total=len(event_tuple),
            negative_to_positive_events=directions[LiveCrossingDirection.NEGATIVE_TO_POSITIVE],
            positive_to_negative_events=directions[LiveCrossingDirection.POSITIVE_TO_NEGATIVE],
            frames_with_events=len({event.frame_sequence for event in event_tuple}),
            events_near_endpoints=sum(
                _near_endpoint(event, candidate, plan.near_endpoint_distance)
                for event in event_tuple
            ),
            events_after_gaps=events_after_gaps,
            events_after_large_gaps=events_after_large_gaps,
            events_by_lifecycle=tuple(
                LifecycleEventTotal(lifecycle_id, count)
                for lifecycle_id, count in sorted(lifecycle_counts.items())
            ),
            states_expired=None,
            replay_duration_seconds=replay.duration_seconds,
            event_density_per_second=(
                len(event_tuple) / replay.duration_seconds if replay.duration_seconds else 0.0
            ),
            events_per_track_ratio=(len(event_tuple) / len(tracks) if tracks else 0.0),
            gap_count=gap_count,
            maximum_gap=maximum_gap,
            event_after_gap_ratio=(events_after_gaps / len(event_tuple) if event_tuple else 0.0),
            evaluation_latency_ms=max(0.0, float(self._monotonic()) - started) * 1000,
            deterministic_event_fingerprint=_event_fingerprint(event_tuple),
            ground_truth_metrics=ground_truth_metrics,
            errors=(),
            limitations=tuple(sorted(limitations)),
        )

    @staticmethod
    def _rank(
        plan: LineEvaluationPlan,
        replay: TrackingReplay,
        results: tuple[CandidateEvaluationResult, ...],
    ) -> tuple[tuple[str, ...], str | None, str]:
        if plan.ranking_method is LineRankingMethod.NO_AUTOMATIC_RECOMMENDATION:
            return (), None, "Automatic recommendation is disabled by the evaluation plan."
        if not replay.ground_truth_events:
            return (), None, "No recommendation can be made based on accuracy without ground truth."
        ranked = tuple(
            result.candidate_id
            for result in sorted(
                results,
                key=lambda result: _candidate_sort_key(result, plan.ranking_method),
            )
        )
        recommendation = ranked[0]
        if replay.evidence_level is EvidenceLevel.SYNTHETIC:
            explanation = (
                "Best-performing candidate for this synthetic replay under the selected metric."
            )
        elif replay.evidence_level is EvidenceLevel.CONTROLLED_REPLAY:
            explanation = (
                "Best-performing candidate for this controlled replay under the selected metric."
            )
        else:
            explanation = (
                "Best-performing candidate for this representative replay under the selected "
                "crossing-event metric."
            )
        return ranked, recommendation, explanation

    @staticmethod
    def _warnings(
        replay: TrackingReplay,
        results: tuple[CandidateEvaluationResult, ...],
    ) -> tuple[str, ...]:
        warnings: set[str] = set()
        if replay.evidence_level is EvidenceLevel.SYNTHETIC:
            warnings.add("synthetic_evidence_only")
        elif replay.evidence_level is EvidenceLevel.CONTROLLED_REPLAY:
            warnings.add("controlled_replay_not_representative")
        if not replay.ground_truth_events:
            warnings.add("no_ground_truth_accuracy_metrics")
        for result in results:
            if result.event_after_gap_ratio > _HIGH_GAP_EVENT_RATIO:
                warnings.add(f"candidate_{result.candidate_id}_high_gap_event_ratio")
        return tuple(sorted(warnings))


def mark_report_written(report: LineEvaluationReport) -> LineEvaluationReport:
    """Return an immutable copy whose bounded telemetry records report output."""

    return replace(
        report,
        statistics=replace(report.statistics, report_written=True),
    )


__all__ = ["VirtualLinePositionEvaluator", "mark_report_written"]
