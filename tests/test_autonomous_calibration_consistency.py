from __future__ import annotations

from hogflow.calibration import (
    AutonomousCalibrationSettings,
    CalibrationConfidence,
    DirectionVector,
    LineCandidate,
    TrajectorySummary,
)
from hogflow.calibration.engine import (
    consistency_confidence,
    evaluate_candidate_tracks,
    line_band_agreement,
    relative_spread,
)
from hogflow.counting import LiveCrossingDirection, NormalizedLine, NormalizedPoint


def _summary(
    tracker_id: int,
    start: tuple[float, float],
    end: tuple[float, float],
) -> TrajectorySummary:
    samples = tuple(
        (start[0] + (end[0] - start[0]) * index / 11, start[1] + (end[1] - start[1]) * index / 11)
        for index in range(12)
    )
    displacement = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
    return TrajectorySummary(
        tracker_id=tracker_id,
        first_frame=0,
        last_frame=11,
        first_center=start,
        last_center=end,
        sampled_centers=samples,
        lifetime_frames=12,
        displacement=displacement,
        path_length=displacement,
        continuity_ratio=1.0,
        mean_confidence=0.8,
        edge_touched=False,
    )


def _candidate() -> LineCandidate:
    return LineCandidate(
        candidate_id="line_01",
        line=NormalizedLine(NormalizedPoint(0.1, 0.5), NormalizedPoint(0.9, 0.5)),
        along_position=0.5,
        positive_direction=LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
        edge_penalty=0.0,
    )


def test_candidate_metrics_count_one_forward_crossing_without_operational_counter() -> None:
    metrics = evaluate_candidate_tracks(
        _candidate(),
        (_summary(1, (0.5, 0.1), (0.5, 0.9)),),
        AutonomousCalibrationSettings(),
    )

    assert metrics.expected_crossing_tracks == 1
    assert metrics.forward_crossings == 1
    assert metrics.reverse_crossings == 0
    assert metrics.multiple_crossings == 0


def test_neighbor_band_prefers_stable_candidate() -> None:
    stable = line_band_agreement((50, 51, 51, 52))
    unstable = line_band_agreement((34, 67, 40, 59))

    assert stable > unstable
    assert relative_spread((50, 51, 51, 52)) < relative_spread((34, 67, 40, 59))


def test_confidence_tier_reaches_high_only_with_consistent_evidence() -> None:
    assert (
        consistency_confidence(
            eligible_tracks=8,
            direction_purity=0.9,
            neighbor_agreement=0.9,
            continuity_score=0.9,
            score=0.8,
        )
        is CalibrationConfidence.HIGH
    )
    assert (
        consistency_confidence(
            eligible_tracks=2,
            direction_purity=0.9,
            neighbor_agreement=0.9,
            continuity_score=0.9,
            score=0.8,
        )
        is CalibrationConfidence.INCONCLUSIVE
    )


def test_direction_alignment_is_based_on_line_normal() -> None:
    metrics = evaluate_candidate_tracks(
        _candidate(),
        (_summary(1, (0.5, 0.1), (0.5, 0.9)),),
        AutonomousCalibrationSettings(),
    )

    assert metrics.direction_alignment > 0.99
    assert DirectionVector(0.0, 1.0).dy == 1.0
