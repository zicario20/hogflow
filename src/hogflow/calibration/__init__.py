"""Framework-neutral autonomous counting calibration contracts."""

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
    "CalibrationConfidence",
    "CalibrationStatus",
    "CorridorEstimate",
    "CountingGeometryConfiguration",
    "DirectionVector",
    "LineCandidate",
    "LineCandidateMetrics",
    "TrajectoryObservation",
    "TrajectorySummary",
]
