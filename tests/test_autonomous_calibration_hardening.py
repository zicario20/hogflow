from __future__ import annotations

import math

from hogflow.calibration import (
    AutonomousCalibrationSettings,
    CalibrationConfidence,
    DirectionVector,
    LineCandidate,
    TrajectorySummary,
)
from hogflow.calibration.engine import (
    consistency_confidence,
    count_family_metrics,
    detector_perturbation_agreement,
    evaluate_candidate_tracks,
    line_band_agreement,
)
from hogflow.counting import LiveCrossingDirection, NormalizedLine, NormalizedPoint


def _summary(
    tracker_id: int,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    points: int = 12,
) -> TrajectorySummary:
    samples = tuple(
        (
            start[0] + (end[0] - start[0]) * index / (points - 1),
            start[1] + (end[1] - start[1]) * index / (points - 1),
        )
        for index in range(points)
    )
    displacement = math.hypot(end[0] - start[0], end[1] - start[1])
    return TrajectorySummary(
        tracker_id=tracker_id,
        first_frame=0,
        last_frame=points - 1,
        first_center=start,
        last_center=end,
        sampled_centers=samples,
        lifetime_frames=points,
        displacement=displacement,
        path_length=displacement,
        continuity_ratio=1.0,
        mean_confidence=0.8,
        edge_touched=False,
    )


def _candidate(start_x: float = 0.1, end_x: float = 0.9) -> LineCandidate:
    return LineCandidate(
        candidate_id="line_01",
        line=NormalizedLine(
            NormalizedPoint(start_x, 0.5),
            NormalizedPoint(end_x, 0.5),
        ),
        along_position=0.5,
        positive_direction=LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
        edge_penalty=0.0,
    )


def test_line_family_includes_primary_in_stability() -> None:
    stable = line_band_agreement(51, (50, 51, 51, 52))
    unstable = line_band_agreement(31, (16, 16, 13, 13))

    assert stable > 0.9
    assert unstable < 0.5
    assert count_family_metrics(31, (16, 16, 13, 13)).median == 16.0


def test_detector_family_includes_primary_in_stability() -> None:
    stable = detector_perturbation_agreement(51, (51, 50))
    unstable = detector_perturbation_agreement(29, (19, 19))

    assert stable > 0.9
    assert unstable < 0.5


def test_zero_count_family_is_bounded_and_zero_safe() -> None:
    metrics = count_family_metrics(0, (0, 0))

    assert metrics.minimum == 0
    assert metrics.maximum == 0
    assert metrics.median == 0.0
    assert metrics.relative_spread == 0.0
    assert metrics.primary_agreement == 0.0


def test_corridor_coverage_distinguishes_full_partial_and_zero_segments() -> None:
    settings = AutonomousCalibrationSettings()
    summaries = (
        _summary(1, (0.5, 0.1), (0.5, 0.9)),
        _summary(2, (0.8, 0.1), (0.8, 0.9)),
    )

    full = evaluate_candidate_tracks(_candidate(), summaries, settings)
    partial = evaluate_candidate_tracks(_candidate(0.45, 0.55), summaries, settings)
    zero = evaluate_candidate_tracks(_candidate(0.1, 0.2), summaries, settings)

    assert full.corridor_coverage == 1.0
    assert partial.corridor_coverage == 0.5
    assert zero.corridor_coverage == 0.0


def test_lost_near_line_is_distinct_from_clean_post_line_survival() -> None:
    settings = AutonomousCalibrationSettings()
    clean = evaluate_candidate_tracks(
        _candidate(),
        (_summary(1, (0.5, 0.1), (0.5, 0.9)),),
        settings,
    )
    lost = evaluate_candidate_tracks(
        _candidate(),
        (_summary(2, (0.5, 0.1), (0.5, 0.49)),),
        settings,
    )

    assert clean.lost_near_line_ratio == 0.0
    assert lost.lost_near_line_ratio == 1.0
    assert clean.crossing_local_continuity > lost.crossing_local_continuity


def test_historical_b_like_pattern_cannot_return_high_confidence() -> None:
    result = consistency_confidence(
        eligible_tracks=47,
        direction_purity=0.99,
        neighbor_agreement=line_band_agreement(29, (18, 18, 16, 17)),
        continuity_score=0.95,
        score=0.95,
        detector_agreement=detector_perturbation_agreement(29, (19, 19)),
        corridor_coverage=1.0,
        crossing_local_continuity=0.9,
        lost_near_line_ratio=0.0,
        unique_ratio=1.0,
    )

    assert result is not CalibrationConfidence.HIGH


def test_stable_primary_inclusive_evidence_can_return_high_confidence() -> None:
    result = consistency_confidence(
        eligible_tracks=20,
        direction_purity=0.95,
        neighbor_agreement=line_band_agreement(51, (50, 51, 51, 52)),
        continuity_score=0.9,
        score=0.9,
        detector_agreement=detector_perturbation_agreement(51, (51, 50)),
        corridor_coverage=0.95,
        crossing_local_continuity=0.9,
        lost_near_line_ratio=0.0,
        unique_ratio=0.95,
    )

    assert result is CalibrationConfidence.HIGH


def test_direction_vector_remains_framework_neutral() -> None:
    assert DirectionVector(0.0, 1.0).dy == 1.0
