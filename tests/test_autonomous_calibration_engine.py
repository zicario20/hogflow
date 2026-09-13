from __future__ import annotations

import math

from hogflow.calibration import (
    AutonomousCalibrationEngine,
    AutonomousCalibrationSettings,
    DirectionVector,
    TrajectoryObservation,
    TrajectorySummary,
)
from hogflow.calibration.engine import (
    estimate_corridor,
    estimate_dominant_direction,
    generate_line_candidates,
    select_eligible_trajectories,
)


def _summary(
    tracker_id: int,
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    lifetime: int = 12,
) -> TrajectorySummary:
    samples = tuple(
        (
            start[0] + (end[0] - start[0]) * index / (lifetime - 1),
            start[1] + (end[1] - start[1]) * index / (lifetime - 1),
        )
        for index in range(lifetime)
    )
    displacement = math.hypot(end[0] - start[0], end[1] - start[1])
    return TrajectorySummary(
        tracker_id=tracker_id,
        first_frame=0,
        last_frame=lifetime - 1,
        first_center=start,
        last_center=end,
        sampled_centers=samples,
        lifetime_frames=lifetime,
        displacement=displacement,
        path_length=displacement,
        continuity_ratio=1.0,
        mean_confidence=0.8,
        edge_touched=False,
    )


def test_vertical_flow_estimates_downward_direction_and_high_purity() -> None:
    summaries = tuple(
        _summary(index, (0.25 + index * 0.05, 0.1), (0.25 + index * 0.05, 0.9))
        for index in range(4)
    )

    direction, purity = estimate_dominant_direction(summaries, AutonomousCalibrationSettings())

    assert direction is not None
    assert direction.dx == 0.0
    assert direction.dy > 0.99
    assert purity > 0.99


def test_opposing_flow_is_inconclusive_without_a_dominant_direction() -> None:
    summaries = (
        _summary(1, (0.2, 0.1), (0.2, 0.9)),
        _summary(2, (0.8, 0.9), (0.8, 0.1)),
    )

    direction, purity = estimate_dominant_direction(summaries, AutonomousCalibrationSettings())

    assert direction is None
    assert purity == 0.0


def test_diagonal_candidates_are_perpendicular_to_dominant_direction() -> None:
    direction = DirectionVector(1.0, 1.0)
    corridor = estimate_corridor(
        (
            _summary(1, (0.1, 0.1), (0.8, 0.8)),
            _summary(2, (0.2, 0.1), (0.9, 0.8)),
        ),
        direction,
        AutonomousCalibrationSettings(),
    )

    candidates = generate_line_candidates(corridor, direction, AutonomousCalibrationSettings())

    assert candidates
    for candidate in candidates:
        line_dx = candidate.line.end.x - candidate.line.start.x
        line_dy = candidate.line.end.y - candidate.line.start.y
        assert abs(line_dx * direction.dx + line_dy * direction.dy) < 1e-6


def test_short_and_low_displacement_tracks_are_excluded() -> None:
    settings = AutonomousCalibrationSettings()
    eligible = select_eligible_trajectories(
        (
            _summary(1, (0.2, 0.1), (0.2, 0.9), lifetime=3),
            _summary(2, (0.3, 0.1), (0.3, 0.13)),
            _summary(3, (0.4, 0.1), (0.4, 0.9)),
        ),
        settings,
    )

    assert tuple(item.tracker_id for item in eligible) == (3,)


def test_engine_bounds_track_history_and_track_count() -> None:
    engine = AutonomousCalibrationEngine(
        AutonomousCalibrationSettings(max_tracks=1, maximum_sampled_centers=8)
    )
    for frame in range(100):
        engine.observe(TrajectoryObservation(1, frame, (0.4, frame / 110), 0.8))
        engine.observe(TrajectoryObservation(2, frame, (0.6, frame / 110), 0.8))

    summaries = engine.summaries()

    assert len(summaries) == 1
    assert len(summaries[0].sampled_centers) == 8
