from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from hogflow.calibration import (
    AutonomousCalibrationResult,
    CalibrationConfidence,
    CalibrationStatus,
    CountingGeometryConfiguration,
    DirectionVector,
    TrajectorySummary,
)
from hogflow.core import InputDataError
from hogflow.counting import (
    LiveCrossingDirection,
    NormalizedLine,
    NormalizedPoint,
)


def _line() -> NormalizedLine:
    return NormalizedLine(NormalizedPoint(0.1, 0.5), NormalizedPoint(0.9, 0.5))


def _configuration() -> CountingGeometryConfiguration:
    return CountingGeometryConfiguration(
        detector_artifact_fingerprint="a" * 64,
        detector_configuration_fingerprint="b" * 64,
        tracker_configuration_fingerprint="c" * 64,
        line=_line(),
        positive_direction=LiveCrossingDirection.NEGATIVE_TO_POSITIVE,
        crossing_epsilon=0.005,
        absent_track_retention_updates=30,
        algorithm_version="phase10_3c_a_v1",
        settings_fingerprint="d" * 64,
    )


def _summary(
    *, sampled_centers: tuple[tuple[float, float], ...] = ((0.1, 0.2),)
) -> TrajectorySummary:
    return TrajectorySummary(
        tracker_id=1,
        first_frame=0,
        last_frame=8,
        first_center=(0.1, 0.2),
        last_center=(0.1, 0.8),
        sampled_centers=sampled_centers,
        lifetime_frames=9,
        displacement=0.6,
        path_length=0.6,
        continuity_ratio=1.0,
        mean_confidence=0.8,
        edge_touched=False,
    )


def test_counting_configuration_fingerprint_is_stable_and_path_free() -> None:
    first = _configuration()
    second = _configuration()

    assert first.fingerprint == second.fingerprint
    assert len(first.fingerprint) == 64
    assert "D:" not in first.fingerprint
    assert "models" not in first.fingerprint


def test_calibration_models_are_immutable() -> None:
    direction = DirectionVector(0.0, 1.0)
    with pytest.raises(FrozenInstanceError):
        direction.dx = 1.0  # type: ignore[misc]


def test_trajectory_summary_rejects_more_than_64_sampled_centers() -> None:
    with pytest.raises(InputDataError, match="sampled centers"):
        _summary(sampled_centers=tuple((0.1, 0.2) for _ in range(65)))


def test_result_requires_selected_line_for_ready_status() -> None:
    with pytest.raises(InputDataError, match="selected line"):
        AutonomousCalibrationResult(
            status=CalibrationStatus.READY,
            confidence=CalibrationConfidence.HIGH,
            dominant_direction=DirectionVector(0.0, 1.0),
            direction_purity=0.9,
            eligible_track_count=8,
            selected_line=None,
            selected_positive_direction=None,
            selected_score=0.8,
            corridor=None,
            candidate_metrics=(),
            line_band_counts=(),
            detector_perturbation_counts=(),
            counting_configuration=_configuration(),
            limitations=(),
        )
