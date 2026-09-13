"""Framework-neutral autonomous counting calibration contracts."""

from hogflow.calibration.engine import (
    AutonomousCalibrationEngine,
    AutonomousCalibrationSettings,
    consistency_confidence,
    detector_perturbation_agreement,
    estimate_corridor,
    estimate_dominant_direction,
    evaluate_candidate_tracks,
    generate_line_candidates,
    line_band_agreement,
    relative_spread,
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
from hogflow.calibration.video_selection import (
    AutonomousCandidateSuitability,
    AutonomousVideoSelection,
    select_autonomous_demo_candidate,
)

__all__ = [
    "AutonomousCalibrationResult",
    "AutonomousCalibrationEngine",
    "AutonomousCalibrationSettings",
    "AutonomousCandidateSuitability",
    "AutonomousVideoSelection",
    "consistency_confidence",
    "detector_perturbation_agreement",
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
    "evaluate_candidate_tracks",
    "generate_line_candidates",
    "line_band_agreement",
    "relative_spread",
    "select_eligible_trajectories",
    "select_autonomous_demo_candidate",
]
