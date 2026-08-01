"""Immutable, path-free models for controlled real-video validation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields
from datetime import datetime
from enum import Enum
from math import isfinite
from re import fullmatch
from typing import Any

from hogflow.counting import LiveCrossingDirection
from hogflow.evaluation import EvidenceLevel, LineCandidate, LineEvaluationPlan, LineRankingMethod
from hogflow.validation.errors import ValidationConfigurationError

VALIDATION_SCHEMA_VERSION = "1.0"
VALIDATION_WORKFLOW_VERSION = "1.0"
BLOCKED_EMPIRICAL_VERDICT = "REAL DETECTOR VALIDATION COULD NOT BE COMPLETED"
DETECTOR_ONLY_EMPIRICAL_VERDICT = (
    "REAL DETECTOR VALIDATION SUCCEEDED, COUNTING ACCURACY REMAINS UNKNOWN"
)
DETECTOR_AND_COUNTING_EMPIRICAL_VERDICT = "REAL DETECTOR AND COUNTING VALIDATION SUCCEEDED"
VIDEO_3_COUNTING_WARNING = "NOT VALID FOR COUNTING ACCURACY"
_EMPIRICAL_VERDICTS = frozenset(
    {
        BLOCKED_EMPIRICAL_VERDICT,
        DETECTOR_ONLY_EMPIRICAL_VERDICT,
        DETECTOR_AND_COUNTING_EMPIRICAL_VERDICT,
    }
)

_OPAQUE_ID = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
_SHA256 = r"[0-9a-f]{64}"
_MAX_TEXT = 320
_MAX_CALIBRATION_CANDIDATES = 64
_MAX_LIMITATIONS = 32


class EvidenceState(str, Enum):
    """Provenance state for one scalar result value."""

    MEASURED = "measured"
    PROVIDED_MANUAL_GROUND_TRUTH = "provided_manual_ground_truth"
    DERIVED = "derived"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class ValidationVideoRole(str, Enum):
    """Authorized purpose of one local video in Phase 10.3."""

    PRIMARY_COUNTING_REFERENCE = "primary_counting_reference"
    SECONDARY_DIFFICULT_COUNTING = "secondary_difficult_counting"
    DETECTION_TRACKING_STRESS_ONLY = "detection_tracking_stress_only"


class ValidationRunStatus(str, Enum):
    """Structural completion state of one video run."""

    COMPLETED = "completed"
    BLOCKED = "blocked"
    INCOMPLETE = "incomplete"


class ModelGateState(str, Enum):
    """Outcome of the approved local-model artifact gate."""

    AVAILABLE = "available"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    REJECTED = "rejected"


def _opaque(value: object, name: str) -> str:
    if not isinstance(value, str) or fullmatch(_OPAQUE_ID, value) is None:
        raise ValidationConfigurationError(f"{name} must be a sanitized opaque identifier.")
    return value


def _sha256(value: object, name: str) -> str:
    if not isinstance(value, str) or fullmatch(_SHA256, value) is None:
        raise ValidationConfigurationError(f"{name} must be a lowercase SHA-256 fingerprint.")
    return value


def _text(value: object, name: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or len(value) > _MAX_TEXT
        or any(token in value for token in ("\r", "\n", "\x00", "\\", "/", "://"))
    ):
        raise ValidationConfigurationError(f"{name} must be short sanitized text.")
    return value


def _non_negative_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValidationConfigurationError(f"{name} must be a non-negative integer.")
    return value


def _positive_int(value: object, name: str) -> int:
    number = _non_negative_int(value, name)
    if number == 0:
        raise ValidationConfigurationError(f"{name} must be positive.")
    return number


def _finite_number(value: object, name: str, *, minimum: float = 0.0) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or float(value) < minimum
    ):
        raise ValidationConfigurationError(
            f"{name} must be finite and greater than or equal to {minimum}."
        )
    return float(value)


def _canonical(value: object) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    return value


def canonical_fingerprint(value: object) -> str:
    """Return a deterministic path-free SHA-256 fingerprint."""

    payload = json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EvidenceValue:
    """One scalar value with an explicit evidence provenance state."""

    state: EvidenceState
    value: int | float | str | bool | None = None
    unit: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.state, EvidenceState):
            raise ValidationConfigurationError("Evidence state must be explicit.")
        unavailable = self.state in {EvidenceState.UNKNOWN, EvidenceState.NOT_APPLICABLE}
        if unavailable != (self.value is None):
            raise ValidationConfigurationError(
                "Unknown and not-applicable evidence must omit a value; other states require one."
            )
        if isinstance(self.value, float) and not isfinite(self.value):
            raise ValidationConfigurationError("Evidence values must be finite.")
        if self.value is not None and not isinstance(self.value, (int, float, str, bool)):
            raise ValidationConfigurationError("Evidence values must be scalar and serializable.")
        if isinstance(self.value, str):
            _text(self.value, "Evidence value")
        if self.unit is not None:
            _opaque(self.unit, "Evidence unit")

    @classmethod
    def measured(cls, value: int | float | str | bool, unit: str | None = None) -> EvidenceValue:
        return cls(EvidenceState.MEASURED, value, unit)

    @classmethod
    def provided(cls, value: int | float | str | bool, unit: str | None = None) -> EvidenceValue:
        return cls(EvidenceState.PROVIDED_MANUAL_GROUND_TRUTH, value, unit)

    @classmethod
    def derived(cls, value: int | float | str | bool, unit: str | None = None) -> EvidenceValue:
        return cls(EvidenceState.DERIVED, value, unit)

    @classmethod
    def unknown(cls, unit: str | None = None) -> EvidenceValue:
        return cls(EvidenceState.UNKNOWN, None, unit)

    @classmethod
    def not_applicable(cls, unit: str | None = None) -> EvidenceValue:
        return cls(EvidenceState.NOT_APPLICABLE, None, unit)


@dataclass(frozen=True, slots=True)
class AuthorizedVideo:
    """Path-free identity and authorized role for one exact local video."""

    video_id: str
    role: ValidationVideoRole
    candidate_classifications: tuple[str, ...]
    counting_accuracy_eligible: bool

    def __post_init__(self) -> None:
        _opaque(self.video_id, "Video ID")
        if not isinstance(self.role, ValidationVideoRole):
            raise ValidationConfigurationError("Video role must be explicit.")
        if (
            not isinstance(self.candidate_classifications, tuple)
            or not self.candidate_classifications
            or len(self.candidate_classifications) > 8
        ):
            raise ValidationConfigurationError("Video classifications must be a non-empty tuple.")
        normalized = tuple(sorted(self.candidate_classifications))
        if len(set(normalized)) != len(normalized):
            raise ValidationConfigurationError("Video classifications must be unique.")
        for value in normalized:
            _opaque(value, "Video classification")
        object.__setattr__(self, "candidate_classifications", normalized)
        if not isinstance(self.counting_accuracy_eligible, bool):
            raise ValidationConfigurationError("Counting eligibility must be boolean.")
        if (
            self.role is ValidationVideoRole.DETECTION_TRACKING_STRESS_ONLY
            and self.counting_accuracy_eligible
        ):
            raise ValidationConfigurationError("The stress-only video cannot be counting eligible.")


@dataclass(frozen=True, slots=True)
class SanitizedVideoMetadata:
    """Bounded local metadata without a filename or filesystem path."""

    container_format: EvidenceValue
    file_size_bytes: EvidenceValue
    duration_seconds: EvidenceValue
    nominal_fps: EvidenceValue
    frame_count: EvidenceValue
    frame_width: EvidenceValue
    frame_height: EvidenceValue
    readable: EvidenceValue
    stability_label: EvidenceValue

    def __post_init__(self) -> None:
        for field in fields(self):
            if not isinstance(getattr(self, field.name), EvidenceValue):
                raise ValidationConfigurationError("Video metadata values require evidence states.")


@dataclass(frozen=True, slots=True)
class ModelAvailability:
    """Sanitized result of searching approved ignored local model locations."""

    state: ModelGateState
    compatible_artifact_count: int
    sanitized_model_identity: str | None = None
    model_format: str | None = None
    artifact_fingerprint: str | None = None
    reason_code: str = "compatible_model_missing"

    def __post_init__(self) -> None:
        if not isinstance(self.state, ModelGateState):
            raise ValidationConfigurationError("Model gate state must be explicit.")
        _non_negative_int(self.compatible_artifact_count, "Compatible artifact count")
        _opaque(self.reason_code, "Model gate reason")
        if self.state is ModelGateState.AVAILABLE:
            if self.compatible_artifact_count != 1:
                raise ValidationConfigurationError("Available model gate requires one artifact.")
            _opaque(self.sanitized_model_identity, "Sanitized model identity")
            _opaque(self.model_format, "Model format")
            _sha256(self.artifact_fingerprint, "Model artifact fingerprint")
        elif any(
            value is not None
            for value in (
                self.sanitized_model_identity,
                self.model_format,
                self.artifact_fingerprint,
            )
        ):
            raise ValidationConfigurationError(
                "Unavailable model gates cannot expose artifact metadata."
            )


@dataclass(frozen=True, slots=True)
class CalibrationCandidate:
    """One offline detector/tracker/line candidate for one authorized video."""

    candidate_id: str
    video_id: str
    line_candidate: LineCandidate
    positive_direction: LiveCrossingDirection
    confidence_threshold: float
    iou_threshold: float
    inference_image_size: int
    tracker_frame_rate: float
    lost_track_buffer: int
    maximum_detections: int

    def __post_init__(self) -> None:
        _opaque(self.candidate_id, "Calibration candidate ID")
        _opaque(self.video_id, "Calibration video ID")
        if not isinstance(self.line_candidate, LineCandidate):
            raise ValidationConfigurationError("Calibration line candidate is invalid.")
        if not isinstance(self.positive_direction, LiveCrossingDirection):
            raise ValidationConfigurationError("Positive direction must be explicit.")
        for name in ("confidence_threshold", "iou_threshold"):
            value = _finite_number(getattr(self, name), name)
            if value > 1:
                raise ValidationConfigurationError(f"{name} must be from 0 through 1.")
            object.__setattr__(self, name, value)
        _positive_int(self.inference_image_size, "Inference image size")
        object.__setattr__(
            self,
            "tracker_frame_rate",
            _finite_number(self.tracker_frame_rate, "Tracker frame rate", minimum=0.000001),
        )
        _non_negative_int(self.lost_track_buffer, "Lost-track buffer")
        _positive_int(self.maximum_detections, "Maximum detections")

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(self)


@dataclass(frozen=True, slots=True)
class CalibrationPlan:
    """Deterministic per-video plan that never mutates live defaults."""

    plan_id: str
    video_id: str
    candidates: tuple[CalibrationCandidate, ...]

    def __post_init__(self) -> None:
        _opaque(self.plan_id, "Calibration plan ID")
        _opaque(self.video_id, "Calibration video ID")
        if (
            not isinstance(self.candidates, tuple)
            or not self.candidates
            or len(self.candidates) > _MAX_CALIBRATION_CANDIDATES
        ):
            raise ValidationConfigurationError("Calibration plan requires candidates.")
        if not all(isinstance(item, CalibrationCandidate) for item in self.candidates):
            raise ValidationConfigurationError("Calibration plan candidates are invalid.")
        ordered = tuple(sorted(self.candidates, key=lambda item: item.candidate_id))
        if len({item.candidate_id for item in ordered}) != len(ordered):
            raise ValidationConfigurationError("Calibration candidate IDs must be unique.")
        if any(item.video_id != self.video_id for item in ordered):
            raise ValidationConfigurationError("Calibration candidates cannot mix videos.")
        object.__setattr__(self, "candidates", ordered)

    @property
    def fingerprint(self) -> str:
        return canonical_fingerprint(self)

    def line_evaluation_plan(self) -> LineEvaluationPlan:
        """Reuse Phase 6 configuration without making an automatic recommendation."""

        return LineEvaluationPlan(
            plan_id=f"{self.plan_id}.lines",
            candidates=tuple(item.line_candidate for item in self.candidates),
            ranking_method=LineRankingMethod.NO_AUTOMATIC_RECOMMENDATION,
            metadata=(("video_id", self.video_id),),
        )


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    model_load_duration_ms: EvidenceValue
    first_inference_latency_ms: EvidenceValue
    steady_state_inference_latency_ms: EvidenceValue
    total_processing_latency_ms: EvidenceValue
    average_fps: EvidenceValue
    minimum_fps: EvidenceValue
    maximum_fps: EvidenceValue
    frames_processed: EvidenceValue
    video_frames_expected: EvidenceValue
    frames_dropped: EvidenceValue

    def __post_init__(self) -> None:
        _metrics(self)


@dataclass(frozen=True, slots=True)
class DetectorDiagnostics:
    detections_produced: EvidenceValue
    frames_with_detections: EvidenceValue
    source_failures: EvidenceValue
    detector_failures: EvidenceValue
    temporary_inference_failures: EvidenceValue
    malformed_outputs: EvidenceValue

    def __post_init__(self) -> None:
        _metrics(self)


@dataclass(frozen=True, slots=True)
class TrackingDiagnostics:
    temporary_track_ids_observed: EvidenceValue
    average_tracks_per_frame: EvidenceValue
    maximum_tracks_per_frame: EvidenceValue
    fragmentations: EvidenceValue
    suspected_id_switches: EvidenceValue
    tracks_lost_near_line: EvidenceValue
    tracker_failures: EvidenceValue
    tracker_resets: EvidenceValue
    reconnects: EvidenceValue

    def __post_init__(self) -> None:
        _metrics(self)


@dataclass(frozen=True, slots=True)
class CrossingCountingDiagnostics:
    crossing_events: EvidenceValue
    accepted_positive_counts: EvidenceValue
    duplicate_positive_events: EvidenceValue
    reverse_events: EvidenceValue
    ignored_events: EvidenceValue
    events_after_frame_gaps: EvidenceValue
    stale_evidence_rejected: EvidenceValue
    crossing_failures: EvidenceValue
    lifecycle_resets: EvidenceValue
    system_count: EvidenceValue

    def __post_init__(self) -> None:
        _metrics(self)


@dataclass(frozen=True, slots=True)
class GroundTruthAssessment:
    manual_total: EvidenceValue
    signed_count_difference: EvidenceValue
    absolute_count_error: EvidenceValue
    percentage_count_error: EvidenceValue
    detector_precision: EvidenceValue
    detector_recall: EvidenceValue
    detector_f1: EvidenceValue

    def __post_init__(self) -> None:
        _metrics(self)

    @classmethod
    def build(
        cls,
        *,
        system_count: EvidenceValue,
        manual_total: int | None,
        counting_applicable: bool,
    ) -> GroundTruthAssessment:
        if not counting_applicable:
            na = EvidenceValue.not_applicable()
            return cls(na, na, na, na, na, na, na)
        detector_unknown = EvidenceValue.unknown()
        if manual_total is None:
            unknown = EvidenceValue.unknown("count")
            return cls(
                unknown,
                unknown,
                unknown,
                EvidenceValue.unknown("percent"),
                detector_unknown,
                detector_unknown,
                detector_unknown,
            )
        _non_negative_int(manual_total, "Manual ground-truth total")
        provided = EvidenceValue.provided(manual_total, "count")
        if (
            system_count.state is not EvidenceState.MEASURED
            or not isinstance(system_count.value, int)
            or isinstance(system_count.value, bool)
        ):
            return cls(
                provided,
                EvidenceValue.unknown("count"),
                EvidenceValue.unknown("count"),
                EvidenceValue.unknown("percent"),
                detector_unknown,
                detector_unknown,
                detector_unknown,
            )
        difference = system_count.value - manual_total
        percentage = (
            EvidenceValue.derived(abs(difference) / manual_total * 100.0, "percent")
            if manual_total > 0
            else EvidenceValue.unknown("percent")
        )
        return cls(
            provided,
            EvidenceValue.derived(difference, "count"),
            EvidenceValue.derived(abs(difference), "count"),
            percentage,
            detector_unknown,
            detector_unknown,
            detector_unknown,
        )


def _metrics(value: object) -> None:
    if not all(isinstance(getattr(value, field.name), EvidenceValue) for field in fields(value)):
        raise ValidationConfigurationError("Diagnostic fields require explicit evidence states.")


@dataclass(frozen=True, slots=True)
class VideoValidationResult:
    """One separate sanitized result for one authorized video."""

    run_id: str
    video: AuthorizedVideo
    evidence_level: EvidenceLevel
    status: ValidationRunStatus
    metadata: SanitizedVideoMetadata
    model_availability: ModelAvailability
    detector_configuration_fingerprint: str | None
    tracker_configuration_fingerprint: str | None
    calibration_candidate: CalibrationCandidate | None
    runtime_device: str | None
    performance: PerformanceMetrics
    detector: DetectorDiagnostics
    tracking: TrackingDiagnostics
    crossing_counting: CrossingCountingDiagnostics
    ground_truth: GroundTruthAssessment
    structurally_complete: bool
    limitations: tuple[str, ...]
    conclusion: str
    schema_version: str = VALIDATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _opaque(self.run_id, "Validation run ID")
        if self.schema_version != VALIDATION_SCHEMA_VERSION:
            raise ValidationConfigurationError("Validation schema version is unsupported.")
        if not isinstance(self.video, AuthorizedVideo):
            raise ValidationConfigurationError("Validation video is invalid.")
        if not isinstance(self.evidence_level, EvidenceLevel):
            raise ValidationConfigurationError("Evidence level must be explicit.")
        if not isinstance(self.status, ValidationRunStatus):
            raise ValidationConfigurationError("Validation status must be explicit.")
        if not isinstance(self.metadata, SanitizedVideoMetadata):
            raise ValidationConfigurationError("Validation metadata is invalid.")
        if not isinstance(self.model_availability, ModelAvailability):
            raise ValidationConfigurationError("Model availability is invalid.")
        for value, name in (
            (self.detector_configuration_fingerprint, "Detector configuration fingerprint"),
            (self.tracker_configuration_fingerprint, "Tracker configuration fingerprint"),
        ):
            if value is not None:
                _sha256(value, name)
        if self.calibration_candidate is not None and (
            not isinstance(self.calibration_candidate, CalibrationCandidate)
            or self.calibration_candidate.video_id != self.video.video_id
        ):
            raise ValidationConfigurationError("Calibration candidate does not match the video.")
        if self.runtime_device is not None:
            _opaque(self.runtime_device, "Runtime device")
        for value in (
            self.performance,
            self.detector,
            self.tracking,
            self.crossing_counting,
            self.ground_truth,
        ):
            if not hasattr(value, "__dataclass_fields__"):
                raise ValidationConfigurationError("Validation diagnostic group is invalid.")
        if not isinstance(self.structurally_complete, bool):
            raise ValidationConfigurationError("Structural completion must be boolean.")
        if (
            not isinstance(self.limitations, tuple)
            or not self.limitations
            or len(self.limitations) > _MAX_LIMITATIONS
        ):
            raise ValidationConfigurationError("Validation limitations must be a non-empty tuple.")
        normalized = tuple(
            sorted({_text(item, "Validation limitation") for item in self.limitations})
        )
        object.__setattr__(self, "limitations", normalized)
        _text(self.conclusion, "Validation conclusion")
        if not self.video.counting_accuracy_eligible:
            if self.crossing_counting.system_count.state is not EvidenceState.NOT_APPLICABLE:
                raise ValidationConfigurationError(
                    "Stress-only video count must be not applicable."
                )
            if VIDEO_3_COUNTING_WARNING not in self.limitations:
                raise ValidationConfigurationError(
                    "Stress-only result requires its counting warning."
                )

    @property
    def run_fingerprint(self) -> str:
        return canonical_fingerprint(self)


@dataclass(frozen=True, slots=True)
class RealWorldValidationReport:
    """Deterministic sanitized report containing one result per authorized video."""

    report_id: str
    generated_at: datetime
    model_availability: ModelAvailability
    results: tuple[VideoValidationResult, ...]
    empirical_verdict: str
    schema_version: str = VALIDATION_SCHEMA_VERSION
    workflow_version: str = VALIDATION_WORKFLOW_VERSION

    def __post_init__(self) -> None:
        _opaque(self.report_id, "Validation report ID")
        if not isinstance(self.generated_at, datetime) or self.generated_at.tzinfo is None:
            raise ValidationConfigurationError("Report generation time must be timezone-aware.")
        if (
            self.schema_version != VALIDATION_SCHEMA_VERSION
            or self.workflow_version != VALIDATION_WORKFLOW_VERSION
        ):
            raise ValidationConfigurationError("Validation report version is unsupported.")
        if not isinstance(self.model_availability, ModelAvailability):
            raise ValidationConfigurationError("Report model availability is invalid.")
        if not isinstance(self.results, tuple) or len(self.results) != 3:
            raise ValidationConfigurationError(
                "Report requires exactly three separate video results."
            )
        if tuple(item.video.video_id for item in self.results) != ("video_1", "video_2", "video_3"):
            raise ValidationConfigurationError(
                "Validation results must preserve authorized video order."
            )
        _text(self.empirical_verdict, "Empirical verdict")
        if self.empirical_verdict not in _EMPIRICAL_VERDICTS:
            raise ValidationConfigurationError("Empirical verdict is not an approved statement.")

    @property
    def report_fingerprint(self) -> str:
        payload = {
            "model_availability": _canonical(self.model_availability),
            "report_id": self.report_id,
            "results": [item.run_fingerprint for item in self.results],
            "schema_version": self.schema_version,
            "workflow_version": self.workflow_version,
        }
        return canonical_fingerprint(payload)


def to_primitive(value: object) -> Any:
    """Expose deterministic JSON-safe values for the reporting boundary."""

    return _canonical(value)


__all__ = [
    "BLOCKED_EMPIRICAL_VERDICT",
    "DETECTOR_AND_COUNTING_EMPIRICAL_VERDICT",
    "DETECTOR_ONLY_EMPIRICAL_VERDICT",
    "VALIDATION_SCHEMA_VERSION",
    "VALIDATION_WORKFLOW_VERSION",
    "VIDEO_3_COUNTING_WARNING",
    "AuthorizedVideo",
    "CalibrationCandidate",
    "CalibrationPlan",
    "CrossingCountingDiagnostics",
    "DetectorDiagnostics",
    "EvidenceState",
    "EvidenceValue",
    "GroundTruthAssessment",
    "ModelAvailability",
    "ModelGateState",
    "PerformanceMetrics",
    "RealWorldValidationReport",
    "SanitizedVideoMetadata",
    "TrackingDiagnostics",
    "ValidationRunStatus",
    "ValidationVideoRole",
    "VideoValidationResult",
    "canonical_fingerprint",
    "to_primitive",
]
