"""Framework-neutral autonomous counting calibration contracts."""

from hogflow.calibration.engine import (
    AutonomousCalibrationEngine,
    AutonomousCalibrationSettings,
    estimate_corridor,
    estimate_dominant_direction,
    generate_line_candidates,
    select_eligible_trajectories,
)
from hogflow.calibration.models import (
    AutonomousCalibrationResult,
    CalibrationConfidence,
    CalibrationStatus,
    CorridorEstimate,
    CountingGeometryConfiguration,
    DirectionVector,
    LineCandidate,
    LineCandidateMetrics,
    TrajectoryObservation,
    TrajectorySummary,
)

__all__ = [
    "AutonomousCalibrationResult",
    "AutonomousCalibrationEngine",
    "AutonomousCalibrationSettings",
    "CalibrationConfidence",
    "CalibrationStatus",
    "CorridorEstimate",
    "CountingGeometryConfiguration",
    "DirectionVector",
    "LineCandidate",
    "LineCandidateMetrics",
    "TrajectoryObservation",
    "TrajectorySummary",
    "estimate_corridor",
    "estimate_dominant_direction",
    "generate_line_candidates",
    "select_eligible_trajectories",
]
