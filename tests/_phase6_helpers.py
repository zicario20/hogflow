from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hogflow.counting import (
    LiveCrossingDirection,
    NormalizedLine,
    NormalizedPoint,
    TrackAnchor,
)
from hogflow.evaluation.line_models import (
    EvidenceLevel,
    GroundTruthCrossingEvent,
    LineCandidate,
    LineEvaluationPlan,
    LineRankingMethod,
    TrackingReplay,
)
from hogflow.models import BoundingBox, Detection, Track
from hogflow.tracking import TrackedObject, TrackingResult

BASE_TIME = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)


def tracked_object(
    tracker_id: int,
    x: float,
    y: float,
    *,
    box_width: float = 10,
    box_height: float = 20,
) -> TrackedObject:
    detection = Detection(
        bounding_box=BoundingBox(
            x - box_width / 2,
            y - box_height,
            x + box_width / 2,
            y,
        ),
        confidence=0.9,
        class_id=0,
        class_name="pig",
    )
    return TrackedObject(track=Track(tracker_id=tracker_id, detection=detection))


def tracking_result(
    sequence: int,
    objects: tuple[TrackedObject, ...] = (),
    *,
    source_id: str = "synthetic-source",
    captured_offset_seconds: float | None = None,
) -> TrackingResult:
    captured_at = BASE_TIME + timedelta(
        seconds=sequence if captured_offset_seconds is None else captured_offset_seconds
    )
    return TrackingResult(
        source_id=source_id,
        frame_sequence=sequence,
        captured_at=captured_at,
        frame_width=100,
        frame_height=100,
        tracked_objects=objects,
        tracker_id="synthetic-tracker",
        tracker_version="1",
        configuration_fingerprint="a" * 64,
        processing_started_at=captured_at,
        processing_finished_at=captured_at,
        tracking_latency_ms=0,
    )


def vertical_candidate(
    candidate_id: str,
    x: float,
    *,
    y_start: float = 0.1,
    y_end: float = 0.9,
    anchor: TrackAnchor = TrackAnchor.BOTTOM_CENTER,
    epsilon: float = 0.001,
    retention: int = 30,
) -> LineCandidate:
    return LineCandidate(
        candidate_id=candidate_id,
        line=NormalizedLine(
            NormalizedPoint(x, y_start),
            NormalizedPoint(x, y_end),
        ),
        anchor=anchor,
        epsilon=epsilon,
        absent_track_retention_updates=retention,
        tags=("synthetic",),
    )


def clean_pass_replay(*, with_ground_truth: bool = True) -> TrackingReplay:
    results = tuple(
        tracking_result(
            sequence,
            (tracked_object(1, x, 50),),
        )
        for sequence, x in enumerate((20, 40, 60, 80))
    )
    ground_truth = (
        (
            GroundTruthCrossingEvent(
                event_id="reference-crossing",
                frame_start=2,
                frame_end=2,
                direction=LiveCrossingDirection.POSITIVE_TO_NEGATIVE,
                provenance="synthetic-reference",
            ),
        )
        if with_ground_truth
        else ()
    )
    return TrackingReplay(
        source_id="synthetic-source",
        replay_id="clean-pass",
        tracker_lifecycle_id="tracker-lifecycle-1",
        tracking_results=results,
        evidence_level=EvidenceLevel.SYNTHETIC,
        provenance="phase6-synthetic-fixture",
        ground_truth_events=ground_truth,
        metadata=(("scenario", "clean_pass"),),
    )


def extension_replay() -> TrackingReplay:
    return TrackingReplay(
        source_id="synthetic-source",
        replay_id="finite-extension",
        tracker_lifecycle_id="tracker-lifecycle-1",
        tracking_results=(
            tracking_result(0, (tracked_object(1, 30, 85),)),
            tracking_result(1, (tracked_object(1, 70, 85),)),
        ),
        evidence_level=EvidenceLevel.SYNTHETIC,
        provenance="phase6-synthetic-fixture",
        metadata=(("scenario", "finite_extension"),),
    )


def jitter_gap_replay() -> TrackingReplay:
    return TrackingReplay(
        source_id="synthetic-source",
        replay_id="jitter-gaps",
        tracker_lifecycle_id="tracker-lifecycle-1",
        tracking_results=(
            tracking_result(
                0,
                (
                    tracked_object(1, 49.8, 45),
                    tracked_object(2, 20, 70),
                ),
                captured_offset_seconds=0,
            ),
            tracking_result(
                1,
                (
                    tracked_object(1, 50.1, 45),
                    tracked_object(2, 25, 70),
                ),
                captured_offset_seconds=0.1,
            ),
            tracking_result(
                5,
                (
                    tracked_object(1, 40, 45),
                    tracked_object(2, 30, 70),
                    tracked_object(3, 20, 55),
                ),
                captured_offset_seconds=0.5,
            ),
            tracking_result(
                12,
                (
                    tracked_object(1, 70, 45),
                    tracked_object(2, 35, 70),
                    tracked_object(3, 80, 55),
                ),
                captured_offset_seconds=1.2,
            ),
        ),
        evidence_level=EvidenceLevel.SYNTHETIC,
        provenance="phase6-synthetic-fixture",
        ground_truth_events=(
            GroundTruthCrossingEvent(
                event_id="gap-crossing-1",
                frame_start=12,
                frame_end=12,
                direction=LiveCrossingDirection.POSITIVE_TO_NEGATIVE,
                provenance="synthetic-reference",
            ),
            GroundTruthCrossingEvent(
                event_id="gap-crossing-3",
                frame_start=12,
                frame_end=12,
                direction=LiveCrossingDirection.POSITIVE_TO_NEGATIVE,
                provenance="synthetic-reference",
            ),
        ),
        metadata=(("scenario", "jitter_and_gaps"),),
    )


def three_candidate_plan(
    *,
    ranking: LineRankingMethod = LineRankingMethod.EVENT_F1,
) -> LineEvaluationPlan:
    return LineEvaluationPlan(
        plan_id="three-vertical-lines",
        candidates=(
            vertical_candidate("line-right", 0.7),
            vertical_candidate("line-center", 0.5),
            vertical_candidate("line-left", 0.3),
        ),
        ranking_method=ranking,
        matching_window_frames=2,
        near_endpoint_distance=0.05,
        metadata=(("fixture", "synthetic"),),
    )


def reference_candidate_plan() -> LineEvaluationPlan:
    return LineEvaluationPlan(
        plan_id="reference-geometries",
        candidates=(
            vertical_candidate("vertical-center", 0.5),
            vertical_candidate("vertical-left", 0.3),
            vertical_candidate("vertical-right", 0.7),
            vertical_candidate("segment-short", 0.5, y_start=0.4, y_end=0.6),
            vertical_candidate("segment-long", 0.5, y_start=0.05, y_end=0.95),
            LineCandidate(
                candidate_id="horizontal",
                line=NormalizedLine(
                    NormalizedPoint(0.1, 0.5),
                    NormalizedPoint(0.9, 0.5),
                ),
            ),
            LineCandidate(
                candidate_id="diagonal",
                line=NormalizedLine(
                    NormalizedPoint(0.1, 0.1),
                    NormalizedPoint(0.9, 0.9),
                ),
            ),
        ),
        ranking_method=LineRankingMethod.NO_AUTOMATIC_RECOMMENDATION,
    )
