"""Framework-neutral bounded models for autonomous counting calibration."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum
from re import fullmatch

from hogflow.core import InputDataError
from hogflow.counting import LiveCrossingDirection, NormalizedLine

_SHA256 = r"[0-9a-f]{64}"
_IDENTIFIER = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
_MAX_SAMPLES = 64


def _finite(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InputDataError(f"{name} must be finite.")
    return float(value)


def _unit(value: object, name: str) -> float:
    result = _finite(value, name)
    if not 0.0 <= result <= 1.0:
        raise InputDataError(f"{name} must be between 0 and 1.")
    return result


def _non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InputDataError(f"{name} must be a non-negative integer.")
    return value


def _positive_int(value: object, name: str) -> int:
    result = _non_negative_int(value, name)
    if result == 0:
        raise InputDataError(f"{name} must be positive.")
    return result


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or fullmatch(_SHA256, value) is None:
        raise InputDataError(f"{name} must be a SHA-256 fingerprint.")
    return value


def _identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or fullmatch(_IDENTIFIER, value) is None:
        raise InputDataError(f"{name} must be sanitized identifier text.")
    return value


def _point(value: object, name: str) -> tuple[float, float]:
    if not isinstance(value, tuple) or len(value) != 2:
        raise InputDataError(f"{name} must be a two-value tuple.")
    return (_unit(value[0], f"{name}.x"), _unit(value[1], f"{name}.y"))


class CalibrationStatus(str, Enum):
    """Terminal status of the autonomous preflight."""

    READY = "ready"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"


class CalibrationConfidence(str, Enum):
    """Confidence in internal calibration consistency, never accuracy."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class DirectionVector:
    """One finite normalized image-space direction vector."""

    dx: float
    dy: float

    def __post_init__(self) -> None:
        dx = _finite(self.dx, "Direction dx")
        dy = _finite(self.dy, "Direction dy")
        magnitude = math.hypot(dx, dy)
        if magnitude <= 1e-9:
            raise InputDataError("Direction vector must have non-zero magnitude.")
        object.__setattr__(self, "dx", dx / magnitude)
        object.__setattr__(self, "dy", dy / magnitude)

    @property
    def magnitude(self) -> float:
        return 1.0

    def dot(self, other: DirectionVector) -> float:
        if not isinstance(other, DirectionVector):
            raise InputDataError("Direction dot product requires a DirectionVector.")
        return self.dx * other.dx + self.dy * other.dy


@dataclass(frozen=True, slots=True)
class TrajectoryObservation:
    """One bounded normalized center observation for a temporary tracker ID."""

    tracker_id: int
    frame_sequence: int
    center: tuple[float, float]
    confidence: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "tracker_id", _non_negative_int(self.tracker_id, "Tracker ID"))
        object.__setattr__(
            self,
            "frame_sequence",
            _non_negative_int(self.frame_sequence, "Frame sequence"),
        )
        object.__setattr__(self, "center", _point(self.center, "Trajectory center"))
        object.__setattr__(self, "confidence", _unit(self.confidence, "Trajectory confidence"))


@dataclass(frozen=True, slots=True)
class TrajectorySummary:
    """Bounded aggregate trajectory evidence for one temporary track."""

    tracker_id: int
    first_frame: int
    last_frame: int
    first_center: tuple[float, float]
    last_center: tuple[float, float]
    sampled_centers: tuple[tuple[float, float], ...]
    lifetime_frames: int
    displacement: float
    path_length: float
    continuity_ratio: float
    mean_confidence: float
    edge_touched: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "tracker_id", _non_negative_int(self.tracker_id, "Tracker ID"))
        first = _non_negative_int(self.first_frame, "First frame")
        last = _non_negative_int(self.last_frame, "Last frame")
        if last < first:
            raise InputDataError("Last frame cannot precede first frame.")
        object.__setattr__(self, "first_frame", first)
        object.__setattr__(self, "last_frame", last)
        object.__setattr__(self, "first_center", _point(self.first_center, "First center"))
        object.__setattr__(self, "last_center", _point(self.last_center, "Last center"))
        if not isinstance(self.sampled_centers, tuple) or len(self.sampled_centers) == 0:
            raise InputDataError("Trajectory requires at least one sampled center.")
        if len(self.sampled_centers) > _MAX_SAMPLES:
            raise InputDataError("Trajectory sampled centers exceed the bounded sample limit.")
        object.__setattr__(
            self,
            "sampled_centers",
            tuple(_point(point, "Sampled center") for point in self.sampled_centers),
        )
        object.__setattr__(self, "lifetime_frames", _positive_int(self.lifetime_frames, "Lifetime"))
        object.__setattr__(self, "displacement", _finite(self.displacement, "Displacement"))
        object.__setattr__(self, "path_length", _finite(self.path_length, "Path length"))
        if self.displacement < 0.0 or self.path_length < 0.0:
            raise InputDataError("Trajectory distances cannot be negative.")
        object.__setattr__(
            self,
            "continuity_ratio",
            _unit(self.continuity_ratio, "Continuity ratio"),
        )
        object.__setattr__(
            self,
            "mean_confidence",
            _unit(self.mean_confidence, "Mean confidence"),
        )
        if not isinstance(self.edge_touched, bool):
            raise InputDataError("Trajectory edge flag must be boolean.")


@dataclass(frozen=True, slots=True)
class CorridorEstimate:
    """Robust normalized along-flow and cross-flow trajectory bounds."""

    reference_center: tuple[float, float]
    along_min: float
    along_max: float
    cross_min: float
    cross_max: float
    dominant_direction: DirectionVector

    def __post_init__(self) -> None:
        reference = _point(self.reference_center, "Corridor reference center")
        along_min = _finite(self.along_min, "Corridor along minimum")
        along_max = _finite(self.along_max, "Corridor along maximum")
        cross_min = _finite(self.cross_min, "Corridor cross minimum")
        cross_max = _finite(self.cross_max, "Corridor cross maximum")
        if not along_min < along_max or not cross_min < cross_max:
            raise InputDataError("Corridor bounds must have positive spans.")
        if not isinstance(self.dominant_direction, DirectionVector):
            raise InputDataError("Corridor direction must be a DirectionVector.")
        object.__setattr__(self, "reference_center", reference)
        object.__setattr__(self, "along_min", along_min)
        object.__setattr__(self, "along_max", along_max)
        object.__setattr__(self, "cross_min", cross_min)
        object.__setattr__(self, "cross_max", cross_max)


@dataclass(frozen=True, slots=True)
class LineCandidate:
    """One finite normalized line candidate perpendicular to motion."""

    candidate_id: str
    line: NormalizedLine
    along_position: float
    positive_direction: LiveCrossingDirection
    edge_penalty: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _identifier(self.candidate_id, "Candidate ID"))
        if not isinstance(self.line, NormalizedLine):
            raise InputDataError("Line candidate requires a NormalizedLine.")
        object.__setattr__(self, "along_position", _unit(self.along_position, "Along position"))
        if not isinstance(self.positive_direction, LiveCrossingDirection):
            raise InputDataError("Candidate positive direction is invalid.")
        object.__setattr__(self, "edge_penalty", _unit(self.edge_penalty, "Edge penalty"))


@dataclass(frozen=True, slots=True)
class CountFamilyMetrics:
    """Robust, bounded summary of one primary count and its variants."""

    minimum: int
    maximum: int
    median: float
    absolute_spread: int
    relative_spread: float
    primary_deviation: float
    primary_agreement: float

    def __post_init__(self) -> None:
        for name in ("minimum", "maximum", "absolute_spread"):
            object.__setattr__(self, name, _non_negative_int(getattr(self, name), name))
        if self.maximum < self.minimum:
            raise InputDataError("Count-family maximum cannot be below minimum.")
        if self.absolute_spread != self.maximum - self.minimum:
            raise InputDataError("Count-family spread must match its bounds.")
        object.__setattr__(self, "median", _finite(self.median, "Count-family median"))
        if self.median < 0.0:
            raise InputDataError("Count-family median cannot be negative.")
        object.__setattr__(self, "relative_spread", _unit(self.relative_spread, "Relative spread"))
        object.__setattr__(
            self, "primary_deviation", _finite(self.primary_deviation, "Primary deviation")
        )
        if self.primary_deviation < 0.0:
            raise InputDataError("Primary deviation cannot be negative.")
        object.__setattr__(
            self, "primary_agreement", _unit(self.primary_agreement, "Primary agreement")
        )


@dataclass(frozen=True, slots=True)
class LineCandidateMetrics:
    """Bounded analysis-only metrics for one candidate line."""

    candidate: LineCandidate
    eligible_tracks: int
    expected_crossing_tracks: int
    forward_crossings: int
    reverse_crossings: int
    multiple_crossings: int
    continuity_score: float
    direction_alignment: float
    corridor_coverage: float
    lost_near_line_ratio: float
    neighbor_counts: tuple[int, ...]
    neighbor_agreement: float
    detector_perturbation_counts: tuple[tuple[float, int], ...]
    perturbation_agreement: float
    score: float
    primary_count: int = 0
    line_count_min: int = 0
    line_count_max: int = 0
    line_count_median: float = 0.0
    line_relative_spread: float = 0.0
    primary_line_agreement: float = 0.0
    detector_variant_counts: tuple[int, ...] = ()
    detector_count_min: int = 0
    detector_count_max: int = 0
    detector_count_median: float = 0.0
    detector_relative_spread: float = 0.0
    primary_detector_agreement: float = 0.0
    crossing_local_continuity: float = 0.0
    confidence_reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, LineCandidate):
            raise InputDataError("Candidate metrics require a LineCandidate.")
        for name in (
            "eligible_tracks",
            "expected_crossing_tracks",
            "forward_crossings",
            "reverse_crossings",
            "multiple_crossings",
        ):
            object.__setattr__(self, name, _non_negative_int(getattr(self, name), name))
        if self.forward_crossings > self.expected_crossing_tracks:
            raise InputDataError("Forward crossings cannot exceed expected crossing tracks.")
        for name in (
            "continuity_score",
            "direction_alignment",
            "corridor_coverage",
            "lost_near_line_ratio",
            "neighbor_agreement",
            "perturbation_agreement",
            "score",
        ):
            object.__setattr__(self, name, _unit(getattr(self, name), name))
        if not isinstance(self.neighbor_counts, tuple) or not self.neighbor_counts:
            raise InputDataError("Candidate metrics require neighbor counts.")
        object.__setattr__(
            self,
            "neighbor_counts",
            tuple(_non_negative_int(value, "Neighbor count") for value in self.neighbor_counts),
        )
        if not isinstance(self.detector_perturbation_counts, tuple):
            raise InputDataError("Detector perturbation counts must be a tuple.")
        perturbations = []
        for confidence, count in self.detector_perturbation_counts:
            perturbations.append(
                (
                    _unit(confidence, "Diagnostic confidence"),
                    _non_negative_int(count, "Diagnostic count"),
                )
            )
        object.__setattr__(self, "detector_perturbation_counts", tuple(perturbations))
        object.__setattr__(
            self, "primary_count", _non_negative_int(self.primary_count, "Primary count")
        )
        for name in (
            "line_count_min",
            "line_count_max",
            "detector_count_min",
            "detector_count_max",
        ):
            object.__setattr__(self, name, _non_negative_int(getattr(self, name), name))
        if self.line_count_max < self.line_count_min:
            raise InputDataError("Line count range is invalid.")
        if self.detector_count_max < self.detector_count_min:
            raise InputDataError("Detector count range is invalid.")
        for name in (
            "line_count_median",
            "detector_count_median",
        ):
            value = _finite(getattr(self, name), name)
            if value < 0.0:
                raise InputDataError(f"{name} cannot be negative.")
            object.__setattr__(self, name, value)
        for name in (
            "line_relative_spread",
            "primary_line_agreement",
            "detector_relative_spread",
            "primary_detector_agreement",
            "crossing_local_continuity",
        ):
            object.__setattr__(self, name, _unit(getattr(self, name), name))
        if not isinstance(self.detector_variant_counts, tuple):
            raise InputDataError("Detector variant counts must be a tuple.")
        variants = tuple(
            _non_negative_int(count, "Detector variant count")
            for count in self.detector_variant_counts
        )
        object.__setattr__(self, "detector_variant_counts", variants)
        if (
            not isinstance(self.confidence_reason_codes, tuple)
            or len(self.confidence_reason_codes) > 16
        ):
            raise InputDataError("Confidence reason codes must be a bounded tuple.")
        for code in self.confidence_reason_codes:
            if not isinstance(code, str) or fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code) is None:
                raise InputDataError("Confidence reason codes must be sanitized identifiers.")

    @property
    def line_count_range(self) -> tuple[int, int]:
        """Return the bounded observed line-family range."""

        return self.line_count_min, self.line_count_max

    @property
    def detector_count_range(self) -> tuple[int, int]:
        """Return the bounded observed detector-family range."""

        return self.detector_count_min, self.detector_count_max


@dataclass(frozen=True, slots=True)
class CountingGeometryConfiguration:
    """Frozen counting geometry provenance for the official second pass."""

    detector_artifact_fingerprint: str
    detector_configuration_fingerprint: str
    tracker_configuration_fingerprint: str
    line: NormalizedLine
    positive_direction: LiveCrossingDirection
    crossing_epsilon: float
    absent_track_retention_updates: int
    algorithm_version: str
    settings_fingerprint: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "detector_artifact_fingerprint",
            _sha(self.detector_artifact_fingerprint, "Detector artifact fingerprint"),
        )
        object.__setattr__(
            self,
            "detector_configuration_fingerprint",
            _sha(self.detector_configuration_fingerprint, "Detector configuration fingerprint"),
        )
        object.__setattr__(
            self,
            "tracker_configuration_fingerprint",
            _sha(self.tracker_configuration_fingerprint, "Tracker configuration fingerprint"),
        )
        if not isinstance(self.line, NormalizedLine):
            raise InputDataError("Counting geometry requires a NormalizedLine.")
        if not isinstance(self.positive_direction, LiveCrossingDirection):
            raise InputDataError("Counting positive direction is invalid.")
        object.__setattr__(
            self, "crossing_epsilon", _unit(self.crossing_epsilon, "Crossing epsilon")
        )
        object.__setattr__(
            self,
            "absent_track_retention_updates",
            _non_negative_int(self.absent_track_retention_updates, "Absent-track retention"),
        )
        object.__setattr__(
            self, "algorithm_version", _identifier(self.algorithm_version, "Algorithm version")
        )
        object.__setattr__(
            self, "settings_fingerprint", _sha(self.settings_fingerprint, "Settings fingerprint")
        )

    @property
    def fingerprint(self) -> str:
        payload = {
            "absent_track_retention_updates": self.absent_track_retention_updates,
            "algorithm_version": self.algorithm_version,
            "crossing_epsilon": self.crossing_epsilon,
            "detector_artifact_fingerprint": self.detector_artifact_fingerprint,
            "detector_configuration_fingerprint": self.detector_configuration_fingerprint,
            "line": {
                "end": {"x": self.line.end.x, "y": self.line.end.y},
                "start": {"x": self.line.start.x, "y": self.line.start.y},
            },
            "positive_direction": self.positive_direction.value,
            "settings_fingerprint": self.settings_fingerprint,
            "tracker_configuration_fingerprint": self.tracker_configuration_fingerprint,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AutonomousCalibrationResult:
    """Path-free bounded result from the autonomous preflight."""

    status: CalibrationStatus
    confidence: CalibrationConfidence
    dominant_direction: DirectionVector | None
    direction_purity: float
    eligible_track_count: int
    selected_line: NormalizedLine | None
    selected_positive_direction: LiveCrossingDirection | None
    selected_score: float
    corridor: CorridorEstimate | None
    candidate_metrics: tuple[LineCandidateMetrics, ...]
    line_band_counts: tuple[int, ...]
    detector_perturbation_counts: tuple[tuple[float, int], ...]
    counting_configuration: CountingGeometryConfiguration | None
    limitations: tuple[str, ...]
    algorithm_version: str = "phase_10_3c_a_v1"
    primary_count: int | None = None
    neighbor_counts: tuple[int, ...] = ()
    line_count_min: int = 0
    line_count_max: int = 0
    line_count_median: float = 0.0
    line_relative_spread: float = 0.0
    primary_line_agreement: float = 0.0
    detector_variant_counts: tuple[int, ...] = ()
    detector_count_min: int = 0
    detector_count_max: int = 0
    detector_count_median: float = 0.0
    detector_relative_spread: float = 0.0
    primary_detector_agreement: float = 0.0
    corridor_coverage: float = 0.0
    lost_near_line_ratio: float = 0.0
    crossing_local_continuity: float = 0.0
    confidence_reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, CalibrationStatus):
            raise InputDataError("Calibration status is invalid.")
        if not isinstance(self.confidence, CalibrationConfidence):
            raise InputDataError("Calibration confidence is invalid.")
        if self.dominant_direction is not None and not isinstance(
            self.dominant_direction, DirectionVector
        ):
            raise InputDataError("Dominant direction is invalid.")
        object.__setattr__(
            self, "direction_purity", _unit(self.direction_purity, "Direction purity")
        )
        object.__setattr__(
            self,
            "eligible_track_count",
            _non_negative_int(self.eligible_track_count, "Eligible track count"),
        )
        if self.selected_line is not None and not isinstance(self.selected_line, NormalizedLine):
            raise InputDataError("Selected line is invalid.")
        if self.selected_positive_direction is not None and not isinstance(
            self.selected_positive_direction, LiveCrossingDirection
        ):
            raise InputDataError("Selected positive direction is invalid.")
        object.__setattr__(self, "selected_score", _unit(self.selected_score, "Selected score"))
        if self.corridor is not None and not isinstance(self.corridor, CorridorEstimate):
            raise InputDataError("Calibration corridor is invalid.")
        if not isinstance(self.candidate_metrics, tuple) or not all(
            isinstance(item, LineCandidateMetrics) for item in self.candidate_metrics
        ):
            raise InputDataError("Candidate metrics must be an immutable tuple.")
        if not isinstance(self.line_band_counts, tuple):
            raise InputDataError("Line-band counts must be a tuple.")
        object.__setattr__(
            self,
            "line_band_counts",
            tuple(_non_negative_int(value, "Line-band count") for value in self.line_band_counts),
        )
        if not isinstance(self.detector_perturbation_counts, tuple):
            raise InputDataError("Detector perturbation counts must be a tuple.")
        perturbations = tuple(
            (
                _unit(confidence, "Diagnostic confidence"),
                _non_negative_int(count, "Diagnostic count"),
            )
            for confidence, count in self.detector_perturbation_counts
        )
        object.__setattr__(self, "detector_perturbation_counts", perturbations)
        if self.status is CalibrationStatus.READY:
            if self.selected_line is None or self.selected_positive_direction is None:
                raise InputDataError("Ready calibration requires a selected line and direction.")
            if self.counting_configuration is None:
                raise InputDataError("Ready calibration requires a counting configuration.")
        if self.counting_configuration is not None and not isinstance(
            self.counting_configuration, CountingGeometryConfiguration
        ):
            raise InputDataError("Counting configuration is invalid.")
        if not isinstance(self.limitations, tuple) or not all(
            isinstance(item, str) and item.strip() for item in self.limitations
        ):
            raise InputDataError("Calibration limitations must be non-empty text tuples.")
        object.__setattr__(
            self, "algorithm_version", _identifier(self.algorithm_version, "Algorithm version")
        )
        if self.primary_count is not None:
            object.__setattr__(
                self, "primary_count", _non_negative_int(self.primary_count, "Primary count")
            )
        if not isinstance(self.neighbor_counts, tuple):
            raise InputDataError("Neighbor counts must be a tuple.")
        object.__setattr__(
            self,
            "neighbor_counts",
            tuple(_non_negative_int(value, "Neighbor count") for value in self.neighbor_counts),
        )
        for name in (
            "line_count_min",
            "line_count_max",
            "detector_count_min",
            "detector_count_max",
        ):
            object.__setattr__(self, name, _non_negative_int(getattr(self, name), name))
        if self.line_count_max < self.line_count_min:
            raise InputDataError("Line count range is invalid.")
        if self.detector_count_max < self.detector_count_min:
            raise InputDataError("Detector count range is invalid.")
        for name in ("line_count_median", "detector_count_median"):
            value = _finite(getattr(self, name), name)
            if value < 0.0:
                raise InputDataError(f"{name} cannot be negative.")
            object.__setattr__(self, name, value)
        for name in (
            "line_relative_spread",
            "primary_line_agreement",
            "detector_relative_spread",
            "primary_detector_agreement",
            "corridor_coverage",
            "lost_near_line_ratio",
            "crossing_local_continuity",
        ):
            object.__setattr__(self, name, _unit(getattr(self, name), name))
        if not isinstance(self.detector_variant_counts, tuple):
            raise InputDataError("Detector variant counts must be a tuple.")
        object.__setattr__(
            self,
            "detector_variant_counts",
            tuple(
                _non_negative_int(count, "Detector variant count")
                for count in self.detector_variant_counts
            ),
        )
        if (
            not isinstance(self.confidence_reason_codes, tuple)
            or len(self.confidence_reason_codes) > 16
        ):
            raise InputDataError("Confidence reason codes must be a bounded tuple.")
        for code in self.confidence_reason_codes:
            if not isinstance(code, str) or fullmatch(r"[A-Z][A-Z0-9_]{0,63}", code) is None:
                raise InputDataError("Confidence reason codes must be sanitized identifiers.")

    @property
    def fingerprint(self) -> str:
        payload = {
            "algorithm_version": self.algorithm_version,
            "candidate_ids": [item.candidate.candidate_id for item in self.candidate_metrics],
            "confidence": self.confidence.value,
            "counting_configuration": (
                None
                if self.counting_configuration is None
                else self.counting_configuration.fingerprint
            ),
            "direction_purity": self.direction_purity,
            "eligible_track_count": self.eligible_track_count,
            "selected_score": self.selected_score,
            "status": self.status.value,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @property
    def line_count_range(self) -> tuple[int, int]:
        """Return the bounded observed line-family range."""

        return self.line_count_min, self.line_count_max

    @property
    def detector_count_range(self) -> tuple[int, int]:
        """Return the bounded observed detector-family range."""

        return self.detector_count_min, self.detector_count_max


__all__ = [
    "AutonomousCalibrationResult",
    "CalibrationConfidence",
    "CalibrationStatus",
    "CountFamilyMetrics",
    "CorridorEstimate",
    "CountingGeometryConfiguration",
    "DirectionVector",
    "LineCandidate",
    "LineCandidateMetrics",
    "TrajectoryObservation",
    "TrajectorySummary",
]
