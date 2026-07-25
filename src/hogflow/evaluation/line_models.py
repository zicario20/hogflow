"""Immutable models for offline virtual-line position evaluation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from re import fullmatch
from statistics import median

from hogflow.core import InputDataError
from hogflow.counting import (
    LiveCrossingConfiguration,
    LiveCrossingDirection,
    NormalizedLine,
    TrackAnchor,
)
from hogflow.evaluation.line_errors import (
    GroundTruthMatchingError,
    LineEvaluationConfigurationError,
    TrackingReplayError,
)
from hogflow.tracking import TrackingResult

LINE_EVALUATION_SCHEMA_VERSION = "1.0"
LINE_EVALUATOR_VERSION = "1.0"

_OPAQUE_ID = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
_TAG = r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}"
_METADATA_KEY = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}"
_SHA256 = r"[0-9a-f]{64}"
_MAX_DESCRIPTION_LENGTH = 240
_MAX_NOTES_LENGTH = 240
_MAX_TAGS = 16
_MAX_METADATA_ITEMS = 16
_MAX_METADATA_VALUE_LENGTH = 160


class EvidenceLevel(str, Enum):
    """Evidence available to one line-position evaluation."""

    SYNTHETIC = "synthetic"
    CONTROLLED_REPLAY = "controlled_replay"
    REPRESENTATIVE_WITHOUT_GROUND_TRUTH = "representative_without_ground_truth"
    REPRESENTATIVE_WITH_GROUND_TRUTH = "representative_with_ground_truth"


class LineRankingMethod(str, Enum):
    """Explicit deterministic line-candidate ranking policy."""

    EVENT_F1 = "event_f1"
    ABSOLUTE_EVENT_COUNT_ERROR = "absolute_event_count_error"
    MEAN_FRAME_OFFSET = "mean_frame_offset"
    NO_AUTOMATIC_RECOMMENDATION = "no_automatic_recommendation"


class LineEvaluationErrorCategory(str, Enum):
    """Sanitized aggregate evaluation error category."""

    NONE = "none"
    CONFIGURATION = "configuration"
    REPLAY = "replay"
    MATCHING = "matching"
    EVALUATION = "evaluation"
    OUTPUT = "output"


def _validate_opaque_id(value: object, name: str) -> str:
    if not isinstance(value, str) or fullmatch(_OPAQUE_ID, value) is None:
        raise InputDataError(f"{name} must be a non-sensitive opaque identifier.")
    return value


def _validate_non_negative_integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InputDataError(f"{name} must be a non-negative integer.")
    return value


def _validate_positive_integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InputDataError(f"{name} must be a positive integer.")
    return value


def _validate_non_negative_number(value: object, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or float(value) < 0
    ):
        raise InputDataError(f"{name} must be a finite non-negative number.")
    return float(value)


def _validate_probability(value: object, name: str) -> float:
    number = _validate_non_negative_number(value, name)
    if number > 1:
        raise InputDataError(f"{name} must be from 0 through 1.")
    return number


def _validate_aware_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InputDataError(f"{name} must be a timezone-aware datetime.")
    return value


def _validate_sanitized_text(
    value: object,
    name: str,
    *,
    maximum_length: int,
    optional: bool = False,
) -> str | None:
    if value is None and optional:
        return None
    if (
        not isinstance(value, str)
        or not value
        or value.strip() != value
        or len(value) > maximum_length
        or any(character in value for character in ("\r", "\n", "\x00"))
    ):
        qualifier = "optional sanitized" if optional else "sanitized"
        raise InputDataError(
            f"{name} must be {qualifier} text no longer than {maximum_length} characters."
        )
    return value


def _validate_metadata(
    metadata: object,
    *,
    error_type: type[InputDataError] = InputDataError,
) -> tuple[tuple[str, str], ...]:
    if not isinstance(metadata, tuple):
        raise error_type("Evaluation metadata must be an immutable tuple.")
    if len(metadata) > _MAX_METADATA_ITEMS:
        raise error_type(f"Evaluation metadata supports at most {_MAX_METADATA_ITEMS} items.")
    normalized: list[tuple[str, str]] = []
    for item in metadata:
        if not isinstance(item, tuple) or len(item) != 2:
            raise error_type("Evaluation metadata entries must be key/value tuples.")
        key, value = item
        if not isinstance(key, str) or fullmatch(_METADATA_KEY, key) is None:
            raise error_type("Evaluation metadata keys must be opaque identifiers.")
        if (
            not isinstance(value, str)
            or not value
            or value.strip() != value
            or len(value) > _MAX_METADATA_VALUE_LENGTH
            or any(character in value for character in ("\r", "\n", "\x00"))
        ):
            raise error_type("Evaluation metadata values must be short sanitized text.")
        normalized.append((key, value))
    normalized_tuple = tuple(sorted(normalized))
    if len({key for key, _value in normalized_tuple}) != len(normalized_tuple):
        raise error_type("Evaluation metadata keys must be unique.")
    return normalized_tuple


def _canonical_hash(payload: object) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LineCandidate:
    """One opaque, immutable virtual-line configuration candidate."""

    candidate_id: str
    line: NormalizedLine
    anchor: TrackAnchor = TrackAnchor.BOTTOM_CENTER
    epsilon: float = 0.005
    absent_track_retention_updates: int = 30
    description: str | None = None
    tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        try:
            _validate_opaque_id(self.candidate_id, "Line candidate ID")
            if not isinstance(self.line, NormalizedLine):
                raise InputDataError("Line candidate geometry must be a NormalizedLine.")
            if not isinstance(self.anchor, TrackAnchor):
                raise InputDataError("Line candidate anchor must be explicit.")
            epsilon = _validate_probability(self.epsilon, "Line candidate epsilon")
            object.__setattr__(self, "epsilon", epsilon)
            _validate_non_negative_integer(
                self.absent_track_retention_updates,
                "Line candidate absent-track retention",
            )
            description = _validate_sanitized_text(
                self.description,
                "Line candidate description",
                maximum_length=_MAX_DESCRIPTION_LENGTH,
                optional=True,
            )
            object.__setattr__(self, "description", description)
            if not isinstance(self.tags, tuple) or len(self.tags) > _MAX_TAGS:
                raise InputDataError(
                    f"Line candidate tags must be an immutable tuple of at most {_MAX_TAGS} items."
                )
            if not all(isinstance(tag, str) and fullmatch(_TAG, tag) for tag in self.tags):
                raise InputDataError("Line candidate tags must be short opaque identifiers.")
            normalized_tags = tuple(sorted(self.tags))
            if len(set(normalized_tags)) != len(normalized_tags):
                raise InputDataError("Line candidate tags must be unique.")
            object.__setattr__(self, "tags", normalized_tags)
        except InputDataError as exc:
            raise LineEvaluationConfigurationError(str(exc)) from exc

    @property
    def fingerprint(self) -> str:
        """Return deterministic sanitized candidate provenance."""

        return _canonical_hash(
            {
                "absent_track_retention_updates": self.absent_track_retention_updates,
                "anchor": self.anchor.value,
                "candidate_id": self.candidate_id,
                "description": self.description,
                "epsilon": self.epsilon,
                "line": {
                    "end": {"x": self.line.end.x, "y": self.line.end.y},
                    "start": {"x": self.line.start.x, "y": self.line.start.y},
                },
                "tags": self.tags,
            }
        )

    def to_live_crossing_configuration(self) -> LiveCrossingConfiguration:
        """Convert explicitly to an enabled live configuration without side effects."""

        return LiveCrossingConfiguration(
            enabled=True,
            line=self.line,
            anchor=self.anchor,
            epsilon=self.epsilon,
            absent_track_retention_updates=self.absent_track_retention_updates,
        )


@dataclass(frozen=True, slots=True)
class LineEvaluationPlan:
    """Validated, canonically ordered set of candidate configurations."""

    plan_id: str
    candidates: tuple[LineCandidate, ...]
    ranking_method: LineRankingMethod = LineRankingMethod.NO_AUTOMATIC_RECOMMENDATION
    matching_window_frames: int = 3
    require_direction_match: bool = True
    near_endpoint_distance: float = 0.025
    large_gap_threshold: int = 10
    schema_version: str = LINE_EVALUATION_SCHEMA_VERSION
    metadata: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        try:
            _validate_opaque_id(self.plan_id, "Line evaluation plan ID")
            if self.schema_version != LINE_EVALUATION_SCHEMA_VERSION:
                raise InputDataError("Line evaluation plan schema version is unsupported.")
            if not isinstance(self.candidates, tuple) or not self.candidates:
                raise InputDataError("Line evaluation plan requires at least one candidate.")
            if not all(isinstance(candidate, LineCandidate) for candidate in self.candidates):
                raise InputDataError("Line evaluation plan candidates are invalid.")
            candidates = tuple(sorted(self.candidates, key=lambda item: item.candidate_id))
            candidate_ids = tuple(candidate.candidate_id for candidate in candidates)
            if len(set(candidate_ids)) != len(candidate_ids):
                raise InputDataError("Line evaluation candidate IDs must be unique.")
            object.__setattr__(self, "candidates", candidates)
            if not isinstance(self.ranking_method, LineRankingMethod):
                raise InputDataError("Line evaluation ranking method must be explicit.")
            _validate_non_negative_integer(
                self.matching_window_frames,
                "Ground-truth matching window",
            )
            if not isinstance(self.require_direction_match, bool):
                raise InputDataError("Direction matching policy must be boolean.")
            near_endpoint = _validate_probability(
                self.near_endpoint_distance,
                "Near-endpoint distance",
            )
            object.__setattr__(self, "near_endpoint_distance", near_endpoint)
            _validate_positive_integer(self.large_gap_threshold, "Large-gap threshold")
            object.__setattr__(
                self,
                "metadata",
                _validate_metadata(self.metadata),
            )
        except InputDataError as exc:
            raise LineEvaluationConfigurationError(str(exc)) from exc

    @property
    def fingerprint(self) -> str:
        """Return an order-independent deterministic plan fingerprint."""

        return _canonical_hash(
            {
                "candidates": [
                    {
                        "candidate_id": candidate.candidate_id,
                        "fingerprint": candidate.fingerprint,
                    }
                    for candidate in self.candidates
                ],
                "large_gap_threshold": self.large_gap_threshold,
                "matching_window_frames": self.matching_window_frames,
                "metadata": self.metadata,
                "near_endpoint_distance": self.near_endpoint_distance,
                "plan_id": self.plan_id,
                "ranking_method": self.ranking_method.value,
                "require_direction_match": self.require_direction_match,
                "schema_version": self.schema_version,
            }
        )


@dataclass(frozen=True, slots=True)
class GroundTruthCrossingEvent:
    """One human or controlled reference crossing independent from tracker identity."""

    event_id: str
    frame_start: int
    frame_end: int
    direction: LiveCrossingDirection | None = None
    timestamp: datetime | None = None
    annotation_quality: float | None = None
    notes: str | None = None
    provenance: str = "unknown"

    def __post_init__(self) -> None:
        try:
            _validate_opaque_id(self.event_id, "Ground-truth event ID")
            _validate_non_negative_integer(self.frame_start, "Ground-truth frame start")
            _validate_non_negative_integer(self.frame_end, "Ground-truth frame end")
            if self.frame_end < self.frame_start:
                raise InputDataError("Ground-truth frame end cannot precede frame start.")
            if self.direction is not None and not isinstance(self.direction, LiveCrossingDirection):
                raise InputDataError("Ground-truth direction must be explicit when supplied.")
            if self.timestamp is not None:
                _validate_aware_datetime(self.timestamp, "Ground-truth timestamp")
            if self.annotation_quality is not None:
                quality = _validate_probability(
                    self.annotation_quality,
                    "Ground-truth annotation quality",
                )
                object.__setattr__(self, "annotation_quality", quality)
            notes = _validate_sanitized_text(
                self.notes,
                "Ground-truth notes",
                maximum_length=_MAX_NOTES_LENGTH,
                optional=True,
            )
            object.__setattr__(self, "notes", notes)
            _validate_opaque_id(self.provenance, "Ground-truth provenance")
        except InputDataError as exc:
            raise TrackingReplayError(str(exc)) from exc


def _tracking_result_payload(result: TrackingResult) -> dict[str, object]:
    return {
        "captured_at": result.captured_at.isoformat(),
        "configuration_fingerprint": result.configuration_fingerprint,
        "frame_height": result.frame_height,
        "frame_sequence": result.frame_sequence,
        "frame_width": result.frame_width,
        "tracked_objects": [
            {
                "age_frames": item.age_frames,
                "bounding_box": {
                    "x_max": item.track.detection.bounding_box.x_max,
                    "x_min": item.track.detection.bounding_box.x_min,
                    "y_max": item.track.detection.bounding_box.y_max,
                    "y_min": item.track.detection.bounding_box.y_min,
                },
                "class_id": item.track.detection.class_id,
                "class_name": item.track.detection.class_name,
                "confidence": item.track.detection.confidence,
                "hits": item.hits,
                "missed_frames": item.missed_frames,
                "source_detection_index": item.source_detection_index,
                "state": item.state.value,
                "tracker_id": item.track.tracker_id,
            }
            for item in result.tracked_objects
        ],
        "tracker_id": result.tracker_id,
        "tracker_version": result.tracker_version,
    }


@dataclass(frozen=True, slots=True)
class TrackingReplay:
    """Immutable ordered tracking sequence for deterministic offline evaluation."""

    source_id: str
    replay_id: str
    tracker_lifecycle_id: str
    tracking_results: tuple[TrackingResult, ...]
    evidence_level: EvidenceLevel
    provenance: str
    ground_truth_events: tuple[GroundTruthCrossingEvent, ...] = ()
    metadata: tuple[tuple[str, str], ...] = ()
    schema_version: str = LINE_EVALUATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        try:
            _validate_opaque_id(self.source_id, "Tracking replay source ID")
            _validate_opaque_id(self.replay_id, "Tracking replay ID")
            _validate_opaque_id(self.tracker_lifecycle_id, "Tracker lifecycle ID")
            _validate_opaque_id(self.provenance, "Tracking replay provenance")
            if self.schema_version != LINE_EVALUATION_SCHEMA_VERSION:
                raise TrackingReplayError("Tracking replay schema version is unsupported.")
            if not isinstance(self.evidence_level, EvidenceLevel):
                raise TrackingReplayError("Tracking replay evidence level must be explicit.")
            if not isinstance(self.tracking_results, tuple) or not self.tracking_results:
                raise TrackingReplayError("Tracking replay requires at least one tracking result.")
            if not all(isinstance(result, TrackingResult) for result in self.tracking_results):
                raise TrackingReplayError(
                    "Tracking replay results must be immutable TrackingResult values."
                )
            previous_sequence: int | None = None
            previous_timestamp: datetime | None = None
            for result in self.tracking_results:
                if result.source_id != self.source_id:
                    raise TrackingReplayError("Tracking replay cannot mix source streams.")
                if previous_sequence is not None and result.frame_sequence <= previous_sequence:
                    raise TrackingReplayError(
                        "Tracking replay frame sequences must increase strictly."
                    )
                if previous_timestamp is not None and result.captured_at < previous_timestamp:
                    raise TrackingReplayError("Tracking replay timestamps must be non-decreasing.")
                previous_sequence = result.frame_sequence
                previous_timestamp = result.captured_at
            if not isinstance(self.ground_truth_events, tuple) or not all(
                isinstance(event, GroundTruthCrossingEvent) for event in self.ground_truth_events
            ):
                raise TrackingReplayError(
                    "Ground-truth crossings must be an immutable event tuple."
                )
            ground_truth = tuple(
                sorted(
                    self.ground_truth_events,
                    key=lambda item: (item.frame_start, item.frame_end, item.event_id),
                )
            )
            if len({event.event_id for event in ground_truth}) != len(ground_truth):
                raise TrackingReplayError("Ground-truth event IDs must be unique.")
            object.__setattr__(self, "ground_truth_events", ground_truth)
            if (
                self.evidence_level is EvidenceLevel.REPRESENTATIVE_WITH_GROUND_TRUTH
                and not ground_truth
            ):
                raise TrackingReplayError(
                    "Representative-with-ground-truth evidence requires reference events."
                )
            if (
                self.evidence_level is EvidenceLevel.REPRESENTATIVE_WITHOUT_GROUND_TRUTH
                and ground_truth
            ):
                raise TrackingReplayError(
                    "Representative-without-ground-truth evidence cannot include reference events."
                )
            object.__setattr__(
                self,
                "metadata",
                _validate_metadata(self.metadata, error_type=TrackingReplayError),
            )
        except InputDataError as exc:
            if isinstance(exc, TrackingReplayError):
                raise
            raise TrackingReplayError(str(exc)) from exc

    @property
    def fingerprint(self) -> str:
        """Return deterministic replay provenance without paths or frame payloads."""

        return _canonical_hash(
            {
                "evidence_level": self.evidence_level.value,
                "ground_truth_events": [
                    {
                        "annotation_quality": event.annotation_quality,
                        "direction": None if event.direction is None else event.direction.value,
                        "event_id": event.event_id,
                        "frame_end": event.frame_end,
                        "frame_start": event.frame_start,
                        "notes": event.notes,
                        "provenance": event.provenance,
                        "timestamp": (
                            None if event.timestamp is None else event.timestamp.isoformat()
                        ),
                    }
                    for event in self.ground_truth_events
                ],
                "metadata": self.metadata,
                "provenance": self.provenance,
                "replay_id": self.replay_id,
                "schema_version": self.schema_version,
                "source_id": self.source_id,
                "tracker_lifecycle_id": self.tracker_lifecycle_id,
                "tracking_results": [
                    _tracking_result_payload(result) for result in self.tracking_results
                ],
            }
        )

    @property
    def duration_seconds(self) -> float:
        """Return observable replay span without interpolating frames."""

        return max(
            0.0,
            (
                self.tracking_results[-1].captured_at - self.tracking_results[0].captured_at
            ).total_seconds(),
        )


@dataclass(frozen=True, slots=True)
class CrossingEventMatch:
    """One deterministic predicted-to-reference crossing match."""

    ground_truth_event_id: str
    predicted_frame_sequence: int
    predicted_tracker_lifecycle_id: str
    predicted_tracker_id: int
    absolute_frame_offset: int
    direction_correct: bool

    def __post_init__(self) -> None:
        _validate_opaque_id(self.ground_truth_event_id, "Matched ground-truth event ID")
        _validate_non_negative_integer(
            self.predicted_frame_sequence,
            "Matched prediction frame",
        )
        _validate_opaque_id(
            self.predicted_tracker_lifecycle_id,
            "Matched prediction lifecycle ID",
        )
        _validate_non_negative_integer(self.predicted_tracker_id, "Matched tracker ID")
        _validate_non_negative_integer(self.absolute_frame_offset, "Match frame offset")
        if not isinstance(self.direction_correct, bool):
            raise GroundTruthMatchingError("Match direction result must be boolean.")


@dataclass(frozen=True, slots=True)
class CrossingEventMetrics:
    """One-to-one crossing-event matching totals and zero-safe metrics."""

    matches: tuple[CrossingEventMatch, ...]
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1_score: float
    mean_absolute_frame_offset: float | None
    median_absolute_frame_offset: float | None
    direction_correct_count: int
    direction_error_count: int
    exact_event_total_difference: int
    absolute_event_count_error: int
    matching_operations: int

    def __post_init__(self) -> None:
        if not isinstance(self.matches, tuple) or not all(
            isinstance(match, CrossingEventMatch) for match in self.matches
        ):
            raise GroundTruthMatchingError("Crossing matches must be an immutable tuple.")
        for name in (
            "true_positives",
            "false_positives",
            "false_negatives",
            "direction_correct_count",
            "direction_error_count",
            "absolute_event_count_error",
            "matching_operations",
        ):
            try:
                _validate_non_negative_integer(getattr(self, name), name)
            except InputDataError as exc:
                raise GroundTruthMatchingError(str(exc)) from exc
        if self.true_positives != len(self.matches):
            raise GroundTruthMatchingError("True positives must equal crossing matches.")
        if self.direction_correct_count + self.direction_error_count != self.true_positives:
            raise GroundTruthMatchingError("Direction totals must equal crossing matches.")
        for name in ("precision", "recall", "f1_score"):
            try:
                _validate_probability(getattr(self, name), name)
            except InputDataError as exc:
                raise GroundTruthMatchingError(str(exc)) from exc
        offsets = tuple(match.absolute_frame_offset for match in self.matches)
        expected_mean = sum(offsets) / len(offsets) if offsets else None
        expected_median = float(median(offsets)) if offsets else None
        for name, supplied, expected in (
            ("mean_absolute_frame_offset", self.mean_absolute_frame_offset, expected_mean),
            (
                "median_absolute_frame_offset",
                self.median_absolute_frame_offset,
                expected_median,
            ),
        ):
            if supplied is None and expected is None:
                continue
            if supplied is None or expected is None or abs(float(supplied) - expected) > 1e-12:
                raise GroundTruthMatchingError(f"{name} is inconsistent with matches.")
        if not isinstance(self.exact_event_total_difference, int) or isinstance(
            self.exact_event_total_difference, bool
        ):
            raise GroundTruthMatchingError("Exact event total difference must be an integer.")
        if abs(self.exact_event_total_difference) != self.absolute_event_count_error:
            raise GroundTruthMatchingError("Absolute event-count error is inconsistent.")
        expected_precision = (
            self.true_positives / (self.true_positives + self.false_positives)
            if self.true_positives + self.false_positives
            else 0.0
        )
        expected_recall = (
            self.true_positives / (self.true_positives + self.false_negatives)
            if self.true_positives + self.false_negatives
            else 0.0
        )
        expected_f1 = (
            2 * expected_precision * expected_recall / (expected_precision + expected_recall)
            if expected_precision + expected_recall
            else 0.0
        )
        for name, supplied, expected in (
            ("precision", self.precision, expected_precision),
            ("recall", self.recall, expected_recall),
            ("f1_score", self.f1_score, expected_f1),
        ):
            if abs(supplied - expected) > 1e-12:
                raise GroundTruthMatchingError(f"{name} is inconsistent with event totals.")


@dataclass(frozen=True, slots=True)
class LifecycleEventTotal:
    """Aggregate event volume for one temporary tracker lifecycle."""

    tracker_lifecycle_id: str
    events_total: int

    def __post_init__(self) -> None:
        _validate_opaque_id(self.tracker_lifecycle_id, "Event lifecycle ID")
        _validate_non_negative_integer(self.events_total, "Lifecycle event total")


@dataclass(frozen=True, slots=True)
class CandidateEvaluationResult:
    """Descriptive and optional reference metrics for one candidate."""

    candidate_id: str
    candidate_fingerprint: str
    tracking_results_processed: int
    tracks_observed: int
    events_total: int
    negative_to_positive_events: int
    positive_to_negative_events: int
    frames_with_events: int
    events_near_endpoints: int
    events_after_gaps: int
    events_after_large_gaps: int
    events_by_lifecycle: tuple[LifecycleEventTotal, ...]
    states_expired: int | None
    replay_duration_seconds: float
    event_density_per_second: float
    events_per_track_ratio: float
    gap_count: int
    maximum_gap: int
    event_after_gap_ratio: float
    evaluation_latency_ms: float
    deterministic_event_fingerprint: str
    ground_truth_metrics: CrossingEventMetrics | None
    errors: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_opaque_id(self.candidate_id, "Candidate result ID")
        if (
            not isinstance(self.candidate_fingerprint, str)
            or fullmatch(_SHA256, self.candidate_fingerprint) is None
        ):
            raise InputDataError("Candidate result fingerprint must be SHA-256 text.")
        for name in (
            "tracking_results_processed",
            "tracks_observed",
            "events_total",
            "negative_to_positive_events",
            "positive_to_negative_events",
            "frames_with_events",
            "events_near_endpoints",
            "events_after_gaps",
            "events_after_large_gaps",
            "gap_count",
            "maximum_gap",
        ):
            _validate_non_negative_integer(getattr(self, name), name)
        if self.events_total != (
            self.negative_to_positive_events + self.positive_to_negative_events
        ):
            raise InputDataError("Candidate direction totals must equal total events.")
        for name in (
            "events_near_endpoints",
            "events_after_gaps",
            "events_after_large_gaps",
            "frames_with_events",
        ):
            if getattr(self, name) > self.events_total:
                raise InputDataError(f"{name} cannot exceed total events.")
        if self.states_expired is not None:
            _validate_non_negative_integer(self.states_expired, "Expired crossing states")
        for name in (
            "replay_duration_seconds",
            "event_density_per_second",
            "events_per_track_ratio",
            "evaluation_latency_ms",
        ):
            _validate_non_negative_number(getattr(self, name), name)
        _validate_probability(self.event_after_gap_ratio, "Event-after-gap ratio")
        if not isinstance(self.events_by_lifecycle, tuple) or not all(
            isinstance(item, LifecycleEventTotal) for item in self.events_by_lifecycle
        ):
            raise InputDataError("Lifecycle event totals must be an immutable tuple.")
        lifecycle_ids = tuple(item.tracker_lifecycle_id for item in self.events_by_lifecycle)
        if lifecycle_ids != tuple(sorted(lifecycle_ids)) or len(set(lifecycle_ids)) != len(
            lifecycle_ids
        ):
            raise InputDataError("Lifecycle event totals must be unique and sorted.")
        if sum(item.events_total for item in self.events_by_lifecycle) != self.events_total:
            raise InputDataError("Lifecycle event totals must equal candidate events.")
        if fullmatch(_SHA256, self.deterministic_event_fingerprint) is None:
            raise InputDataError("Deterministic event fingerprint must be SHA-256 text.")
        if self.ground_truth_metrics is not None and not isinstance(
            self.ground_truth_metrics, CrossingEventMetrics
        ):
            raise InputDataError("Ground-truth crossing metrics are invalid.")
        for name in ("errors", "limitations"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or not all(
                isinstance(value, str) and value and value.strip() == value for value in values
            ):
                raise InputDataError(f"{name} must be an immutable sanitized text tuple.")
            if values != tuple(sorted(set(values))):
                raise InputDataError(f"{name} must be unique and sorted.")


@dataclass(frozen=True, slots=True)
class LineEvaluationStats:
    """Bounded offline-evaluation telemetry, unrelated to live telemetry."""

    candidates_requested: int
    candidates_completed: int
    frames_replayed: int
    total_crossing_updates: int
    total_events_evaluated: int
    matching_operations: int
    evaluation_duration_ms: float
    report_written: bool
    failures: int
    last_error_category: LineEvaluationErrorCategory

    def __post_init__(self) -> None:
        for name in (
            "candidates_requested",
            "candidates_completed",
            "frames_replayed",
            "total_crossing_updates",
            "total_events_evaluated",
            "matching_operations",
            "failures",
        ):
            _validate_non_negative_integer(getattr(self, name), name)
        _validate_non_negative_number(self.evaluation_duration_ms, "Evaluation duration")
        if self.candidates_completed > self.candidates_requested:
            raise InputDataError("Completed candidates cannot exceed requested candidates.")
        if not isinstance(self.report_written, bool):
            raise InputDataError("Report-written state must be boolean.")
        if not isinstance(self.last_error_category, LineEvaluationErrorCategory):
            raise InputDataError("Evaluation error category must be explicit.")


@dataclass(frozen=True, slots=True)
class LineEvaluationReport:
    """Deterministic structured comparison of line candidates for one replay."""

    plan: LineEvaluationPlan
    replay_id: str
    replay_fingerprint: str
    replay_provenance: str
    evidence_level: EvidenceLevel
    ground_truth_available: bool
    candidate_results: tuple[CandidateEvaluationResult, ...]
    ranking_method: LineRankingMethod
    ranked_candidate_ids: tuple[str, ...]
    recommended_candidate_id: str | None
    recommendation_explanation: str
    warnings: tuple[str, ...]
    limitations: tuple[str, ...]
    generated_at: datetime
    statistics: LineEvaluationStats
    schema_version: str = LINE_EVALUATION_SCHEMA_VERSION
    evaluator_version: str = LINE_EVALUATOR_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.plan, LineEvaluationPlan):
            raise InputDataError("Line evaluation report requires a validated plan.")
        _validate_opaque_id(self.replay_id, "Evaluation replay ID")
        if fullmatch(_SHA256, self.replay_fingerprint) is None:
            raise InputDataError("Evaluation replay fingerprint must be SHA-256 text.")
        _validate_opaque_id(self.replay_provenance, "Evaluation replay provenance")
        if not isinstance(self.evidence_level, EvidenceLevel):
            raise InputDataError("Evaluation evidence level must be explicit.")
        if not isinstance(self.ground_truth_available, bool):
            raise InputDataError("Ground-truth availability must be boolean.")
        if not isinstance(self.candidate_results, tuple) or not all(
            isinstance(result, CandidateEvaluationResult) for result in self.candidate_results
        ):
            raise InputDataError("Candidate results must be an immutable tuple.")
        result_ids = tuple(result.candidate_id for result in self.candidate_results)
        expected_ids = tuple(candidate.candidate_id for candidate in self.plan.candidates)
        if result_ids != expected_ids:
            raise InputDataError("Candidate results must match plan candidates in canonical order.")
        if not isinstance(self.ranking_method, LineRankingMethod):
            raise InputDataError("Report ranking method must be explicit.")
        if self.ranking_method is not self.plan.ranking_method:
            raise InputDataError("Report ranking method must match its plan.")
        if (
            not isinstance(self.ranked_candidate_ids, tuple)
            or len(set(self.ranked_candidate_ids)) != len(self.ranked_candidate_ids)
            or any(candidate_id not in expected_ids for candidate_id in self.ranked_candidate_ids)
        ):
            raise InputDataError("Ranked candidate IDs must be a unique plan subset.")
        if self.recommended_candidate_id is not None:
            if (
                not self.ranked_candidate_ids
                or self.recommended_candidate_id != self.ranked_candidate_ids[0]
            ):
                raise InputDataError("Recommended candidate must lead the deterministic ranking.")
        if not self.ground_truth_available and self.recommended_candidate_id is not None:
            raise InputDataError("Accuracy recommendation requires ground truth.")
        if (
            self.ranking_method is LineRankingMethod.NO_AUTOMATIC_RECOMMENDATION
            and self.recommended_candidate_id is not None
        ):
            raise InputDataError("Disabled ranking cannot recommend a candidate.")
        _validate_sanitized_text(
            self.recommendation_explanation,
            "Recommendation explanation",
            maximum_length=320,
        )
        for name in ("warnings", "limitations"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or not all(
                isinstance(value, str) and value and value.strip() == value for value in values
            ):
                raise InputDataError(f"{name} must be an immutable sanitized text tuple.")
            if values != tuple(sorted(set(values))):
                raise InputDataError(f"{name} must be unique and sorted.")
        _validate_aware_datetime(self.generated_at, "Evaluation generation time")
        if not isinstance(self.statistics, LineEvaluationStats):
            raise InputDataError("Evaluation statistics are invalid.")
        if self.schema_version != LINE_EVALUATION_SCHEMA_VERSION:
            raise InputDataError("Evaluation report schema version is unsupported.")
        if self.evaluator_version != LINE_EVALUATOR_VERSION:
            raise InputDataError("Evaluation report evaluator version is unsupported.")


__all__ = [
    "CandidateEvaluationResult",
    "CrossingEventMatch",
    "CrossingEventMetrics",
    "EvidenceLevel",
    "GroundTruthCrossingEvent",
    "LINE_EVALUATION_SCHEMA_VERSION",
    "LINE_EVALUATOR_VERSION",
    "LifecycleEventTotal",
    "LineCandidate",
    "LineEvaluationErrorCategory",
    "LineEvaluationPlan",
    "LineEvaluationReport",
    "LineEvaluationStats",
    "LineRankingMethod",
    "TrackingReplay",
]
