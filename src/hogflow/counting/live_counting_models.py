"""Immutable framework-neutral models for lifecycle directional counting."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from re import fullmatch

from hogflow.core import ConfigurationError, InputDataError
from hogflow.counting.live_models import (
    LiveCrossingDirection,
    LiveCrossingEvent,
    LiveCrossingRunSummary,
    LiveCrossingSnapshot,
)

_SOURCE_ID = r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}"
_OPAQUE_ID = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"
_SHA256 = r"[0-9a-f]{64}"
_SCHEMA_VERSION = "1"


def _opaque_id(value: object, name: str, pattern: str = _OPAQUE_ID) -> str:
    if not isinstance(value, str) or fullmatch(pattern, value) is None:
        raise InputDataError(f"{name} must be opaque text.")
    return value


def _sha256(value: object, name: str) -> str:
    if not isinstance(value, str) or fullmatch(_SHA256, value) is None:
        raise InputDataError(f"{name} must be SHA-256 text.")
    return value


def _non_negative_integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InputDataError(f"{name} must be a non-negative integer.")
    return value


def _positive_integer(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise InputDataError(f"{name} must be a positive integer.")
    return value


def _non_negative_number(value: object, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or float(value) < 0
    ):
        raise InputDataError(f"{name} must be a finite non-negative number.")
    return float(value)


def _aware_datetime(value: object, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise InputDataError(f"{name} must be a timezone-aware datetime.")
    return value


class DuplicateCountingPolicy(str, Enum):
    """Supported behavior for repeated positive events."""

    IGNORE_AFTER_FIRST_POSITIVE = "ignore_after_first_positive"


class ReverseCountingPolicy(str, Enum):
    """Supported behavior for geometrically reverse events."""

    RECORD_WITHOUT_DECREMENT = "record_without_decrement"


class OperationalCrossingDirection(str, Enum):
    """Operational interpretation applied without changing event geometry."""

    POSITIVE = "positive"
    REVERSE = "reverse"


class CountingDecisionType(str, Enum):
    """Auditable outcome for one valid geometric crossing event."""

    COUNTED_POSITIVE = "counted_positive"
    IGNORED_REVERSE = "ignored_reverse"
    IGNORED_DUPLICATE_POSITIVE = "ignored_duplicate_positive"


class LiveCountingHealthState(str, Enum):
    """Bounded lifecycle states for one directional counter."""

    CREATED = "created"
    RUNNING = "running"
    FAILED = "failed"
    STOPPED = "stopped"


class LiveCountingErrorCategory(str, Enum):
    """Sanitized live counting error categories."""

    NONE = "none"
    CONFIGURATION = "configuration"
    INPUT = "input"
    LIFECYCLE = "lifecycle"
    STALE = "stale"
    DUPLICATE_EVENT = "duplicate_event"
    CROSSING_MISMATCH = "crossing_mismatch"
    CAPACITY = "capacity"
    PREVIEW = "preview"
    RESET = "reset"
    CLOSE = "close"


@dataclass(frozen=True, slots=True)
class LiveCountingConfiguration:
    """Validated conservative policy for one crossing lifecycle.

    Counting is disabled by default. When enabled, the positive geometric
    direction and exact Phase 5.4 crossing configuration fingerprint are
    mandatory. Counted identities are never evicted within a lifecycle; the
    configured capacity therefore fails safely before unbounded growth.
    """

    enabled: bool = False
    positive_direction: LiveCrossingDirection | None = None
    crossing_configuration_fingerprint: str | None = None
    duplicate_policy: DuplicateCountingPolicy = DuplicateCountingPolicy.IGNORE_AFTER_FIRST_POSITIVE
    reverse_policy: ReverseCountingPolicy = ReverseCountingPolicy.RECORD_WITHOUT_DECREMENT
    maximum_counted_identities: int = 100_000
    schema_version: str = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ConfigurationError("Counting enabled must be boolean.")
        if self.enabled:
            if not isinstance(self.positive_direction, LiveCrossingDirection):
                raise ConfigurationError(
                    "Enabled counting requires an explicit positive direction."
                )
            try:
                _sha256(
                    self.crossing_configuration_fingerprint,
                    "Crossing configuration fingerprint",
                )
            except InputDataError as exc:
                raise ConfigurationError(str(exc)) from exc
        elif (
            self.positive_direction is not None
            or self.crossing_configuration_fingerprint is not None
        ):
            raise ConfigurationError(
                "Counting policy values require counting to be explicitly enabled."
            )
        if not isinstance(self.duplicate_policy, DuplicateCountingPolicy):
            raise ConfigurationError("Duplicate counting policy must be explicit.")
        if not isinstance(self.reverse_policy, ReverseCountingPolicy):
            raise ConfigurationError("Reverse counting policy must be explicit.")
        try:
            _positive_integer(self.maximum_counted_identities, "Counted-identity capacity")
        except InputDataError as exc:
            raise ConfigurationError(str(exc)) from exc
        if self.schema_version != _SCHEMA_VERSION:
            raise ConfigurationError("Unsupported live counting configuration schema version.")

    @property
    def fingerprint(self) -> str:
        """Return deterministic non-sensitive configuration provenance."""

        payload = {
            "crossing_configuration_fingerprint": self.crossing_configuration_fingerprint,
            "duplicate_policy": self.duplicate_policy.value,
            "enabled": self.enabled,
            "maximum_counted_identities": self.maximum_counted_identities,
            "positive_direction": (
                None if self.positive_direction is None else self.positive_direction.value
            ),
            "reverse_policy": self.reverse_policy.value,
            "schema_version": self.schema_version,
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TemporaryTrackIdentity:
    """Lifecycle-qualified temporary identity, not a biological identity."""

    source_id: str
    crossing_lifecycle_id: str
    tracker_id: int

    def __post_init__(self) -> None:
        _opaque_id(self.source_id, "Temporary identity source ID", _SOURCE_ID)
        _opaque_id(self.crossing_lifecycle_id, "Crossing lifecycle ID")
        _non_negative_integer(self.tracker_id, "Temporary tracker ID")


@dataclass(frozen=True, slots=True)
class LiveCountingDecision:
    """One immutable and auditable decision for a crossing event."""

    identity: TemporaryTrackIdentity
    crossing_event: LiveCrossingEvent
    source_id: str
    counting_lifecycle_id: str
    crossing_lifecycle_id: str
    tracker_id: int
    frame_sequence: int
    previous_frame_sequence: int
    captured_at: datetime
    geometric_direction: LiveCrossingDirection
    operational_direction: OperationalCrossingDirection
    decision_type: CountingDecisionType
    count_increment: int
    total_before: int
    total_after: int
    identity_previously_counted: bool
    counting_configuration_fingerprint: str
    crossing_configuration_fingerprint: str
    line_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, TemporaryTrackIdentity):
            raise InputDataError("Counting decision identity is invalid.")
        if not isinstance(self.crossing_event, LiveCrossingEvent):
            raise InputDataError("Counting decision requires its immutable crossing event.")
        _opaque_id(self.source_id, "Counting decision source ID", _SOURCE_ID)
        _opaque_id(self.counting_lifecycle_id, "Counting lifecycle ID")
        _opaque_id(self.crossing_lifecycle_id, "Crossing lifecycle ID")
        _non_negative_integer(self.tracker_id, "Counting decision tracker ID")
        if (
            self.identity.source_id != self.source_id
            or self.identity.crossing_lifecycle_id != self.crossing_lifecycle_id
            or self.identity.tracker_id != self.tracker_id
        ):
            raise InputDataError("Counting decision identity fields are inconsistent.")
        _non_negative_integer(self.frame_sequence, "Counting decision frame sequence")
        _non_negative_integer(
            self.previous_frame_sequence,
            "Counting decision previous frame sequence",
        )
        if self.previous_frame_sequence >= self.frame_sequence:
            raise InputDataError("Counting decisions require increasing observation frames.")
        _aware_datetime(self.captured_at, "Counting decision capture time")
        if not isinstance(self.geometric_direction, LiveCrossingDirection):
            raise InputDataError("Counting decision geometric direction must be explicit.")
        if not isinstance(self.operational_direction, OperationalCrossingDirection):
            raise InputDataError("Counting decision operational direction must be explicit.")
        if not isinstance(self.decision_type, CountingDecisionType):
            raise InputDataError("Counting decision type must be explicit.")
        if self.count_increment not in (0, 1) or isinstance(self.count_increment, bool):
            raise InputDataError("Counting decision increment must be zero or one.")
        _non_negative_integer(self.total_before, "Counting decision total before")
        _non_negative_integer(self.total_after, "Counting decision total after")
        if self.total_after != self.total_before + self.count_increment:
            raise InputDataError("Counting decision total does not match its increment.")
        if not isinstance(self.identity_previously_counted, bool):
            raise InputDataError("Previous counted-identity state must be boolean.")
        _sha256(
            self.counting_configuration_fingerprint,
            "Counting configuration fingerprint",
        )
        _sha256(
            self.crossing_configuration_fingerprint,
            "Crossing configuration fingerprint",
        )
        _opaque_id(self.line_id, "Counting decision line ID")
        if (
            self.crossing_event.source_id != self.source_id
            or self.crossing_event.crossing_lifecycle_id != self.crossing_lifecycle_id
            or self.crossing_event.tracker_id != self.tracker_id
            or self.crossing_event.frame_sequence != self.frame_sequence
            or self.crossing_event.previous_frame_sequence != self.previous_frame_sequence
            or self.crossing_event.captured_at != self.captured_at
            or self.crossing_event.direction is not self.geometric_direction
            or self.crossing_event.configuration_fingerprint
            != self.crossing_configuration_fingerprint
            or self.crossing_event.line_id != self.line_id
        ):
            raise InputDataError("Counting decision does not preserve its crossing event.")
        self._validate_semantics()

    def _validate_semantics(self) -> None:
        if self.decision_type is CountingDecisionType.COUNTED_POSITIVE:
            if (
                self.operational_direction is not OperationalCrossingDirection.POSITIVE
                or self.count_increment != 1
                or self.identity_previously_counted
            ):
                raise InputDataError("Counted-positive decision fields are inconsistent.")
        elif self.decision_type is CountingDecisionType.IGNORED_DUPLICATE_POSITIVE:
            if (
                self.operational_direction is not OperationalCrossingDirection.POSITIVE
                or self.count_increment != 0
                or not self.identity_previously_counted
            ):
                raise InputDataError("Duplicate-positive decision fields are inconsistent.")
        elif (
            self.operational_direction is not OperationalCrossingDirection.REVERSE
            or self.count_increment != 0
        ):
            raise InputDataError("Reverse decision fields are inconsistent.")


@dataclass(frozen=True, slots=True)
class LiveCountingResult:
    """Atomic decisions and lifecycle total for one crossing-result frame."""

    source_id: str
    counting_lifecycle_id: str
    crossing_lifecycle_id: str
    frame_sequence: int
    captured_at: datetime
    decisions: tuple[LiveCountingDecision, ...]
    frame_increments: int
    lifecycle_directional_count: int
    counted_identities_current: int
    configuration_fingerprint: str
    processing_started_at: datetime
    processing_finished_at: datetime
    counting_latency_ms: float

    def __post_init__(self) -> None:
        _opaque_id(self.source_id, "Counting result source ID", _SOURCE_ID)
        _opaque_id(self.counting_lifecycle_id, "Counting lifecycle ID")
        _opaque_id(self.crossing_lifecycle_id, "Crossing lifecycle ID")
        _non_negative_integer(self.frame_sequence, "Counting result frame sequence")
        _aware_datetime(self.captured_at, "Counting result capture time")
        if not isinstance(self.decisions, tuple) or not all(
            isinstance(item, LiveCountingDecision) for item in self.decisions
        ):
            raise InputDataError("Counting decisions must be an immutable tuple.")
        tracker_ids = [decision.tracker_id for decision in self.decisions]
        if len(tracker_ids) != len(set(tracker_ids)):
            raise InputDataError("One tracker may have at most one counting decision per frame.")
        for decision in self.decisions:
            if (
                decision.source_id != self.source_id
                or decision.counting_lifecycle_id != self.counting_lifecycle_id
                or decision.crossing_lifecycle_id != self.crossing_lifecycle_id
                or decision.frame_sequence != self.frame_sequence
                or decision.captured_at != self.captured_at
                or decision.counting_configuration_fingerprint != self.configuration_fingerprint
            ):
                raise InputDataError("Counting decision does not match its result frame.")
        _non_negative_integer(self.frame_increments, "Counting frame increments")
        if self.frame_increments != sum(item.count_increment for item in self.decisions):
            raise InputDataError("Counting frame increments do not match decisions.")
        _non_negative_integer(
            self.lifecycle_directional_count,
            "Lifecycle directional count",
        )
        _non_negative_integer(
            self.counted_identities_current,
            "Current counted identities",
        )
        if self.lifecycle_directional_count != self.counted_identities_current:
            raise InputDataError("Lifecycle count must equal current counted identities.")
        if self.decisions:
            for previous, current in zip(self.decisions, self.decisions[1:]):
                if current.total_before != previous.total_after:
                    raise InputDataError("Counting decisions must form one atomic total chain.")
            if self.decisions[-1].total_after != self.lifecycle_directional_count:
                raise InputDataError("Counting result total does not match its final decision.")
        _sha256(self.configuration_fingerprint, "Counting result fingerprint")
        _aware_datetime(self.processing_started_at, "Counting processing start")
        _aware_datetime(self.processing_finished_at, "Counting processing finish")
        if self.processing_finished_at < self.processing_started_at:
            raise InputDataError("Counting completion cannot precede its start.")
        object.__setattr__(
            self,
            "counting_latency_ms",
            _non_negative_number(self.counting_latency_ms, "Counting latency"),
        )


@dataclass(frozen=True, slots=True)
class LiveCountingStats:
    """Bounded diagnostics for one lifecycle-aware directional counter."""

    crossing_results_processed: int
    crossing_events_processed: int
    positives_counted: int
    duplicate_positives: int
    reverses: int
    reverses_before_count: int
    reverses_after_count: int
    lifecycle_directional_count: int
    counted_identities_current: int
    counted_identities_peak: int
    frames_without_events: int
    resets: int
    closes: int
    stale_requests_rejected: int
    lifecycle_mismatches: int
    failures: int
    preview_failures: int
    total_counting_latency_ms: float
    average_counting_latency_ms: float
    maximum_counting_latency_ms: float
    last_frame_sequence: int | None
    last_error: LiveCountingErrorCategory
    health_state: LiveCountingHealthState

    def __post_init__(self) -> None:
        for name in (
            "crossing_results_processed",
            "crossing_events_processed",
            "positives_counted",
            "duplicate_positives",
            "reverses",
            "reverses_before_count",
            "reverses_after_count",
            "lifecycle_directional_count",
            "counted_identities_current",
            "counted_identities_peak",
            "frames_without_events",
            "resets",
            "closes",
            "stale_requests_rejected",
            "lifecycle_mismatches",
            "failures",
            "preview_failures",
        ):
            _non_negative_integer(getattr(self, name), name)
        for name in (
            "total_counting_latency_ms",
            "average_counting_latency_ms",
            "maximum_counting_latency_ms",
        ):
            _non_negative_number(getattr(self, name), name)
        if self.last_frame_sequence is not None:
            _non_negative_integer(self.last_frame_sequence, "Last counting frame sequence")
        if not isinstance(self.last_error, LiveCountingErrorCategory):
            raise InputDataError("Last counting error category must be explicit.")
        if not isinstance(self.health_state, LiveCountingHealthState):
            raise InputDataError("Counting health state must be explicit.")
        if self.crossing_events_processed != (
            self.positives_counted + self.duplicate_positives + self.reverses
        ):
            raise InputDataError("Counting event totals are inconsistent.")
        if self.reverses != self.reverses_before_count + self.reverses_after_count:
            raise InputDataError("Counting reverse totals are inconsistent.")
        if self.lifecycle_directional_count != self.counted_identities_current:
            raise InputDataError("Counting lifecycle total must equal counted identities.")


@dataclass(frozen=True, slots=True)
class LiveCountingSnapshot:
    """Current crossing and counting diagnostics without decision history."""

    source_id: str
    counting_lifecycle_id: str
    crossing_lifecycle_id: str
    crossing: LiveCrossingSnapshot
    counting: LiveCountingStats

    def __post_init__(self) -> None:
        _opaque_id(self.source_id, "Counting snapshot source ID", _SOURCE_ID)
        _opaque_id(self.counting_lifecycle_id, "Counting snapshot lifecycle ID")
        _opaque_id(self.crossing_lifecycle_id, "Crossing snapshot lifecycle ID")
        if not isinstance(self.crossing, LiveCrossingSnapshot):
            raise InputDataError("Counting snapshot requires live crossing telemetry.")
        if not isinstance(self.counting, LiveCountingStats):
            raise InputDataError("Counting snapshot statistics are invalid.")


@dataclass(frozen=True, slots=True)
class LiveCountingRunSummary:
    """Terminal state for one live counting lifecycle, not a session."""

    source_id: str
    counting_lifecycle_id: str
    crossing_lifecycle_id: str
    crossing_summary: LiveCrossingRunSummary
    counting_statistics: LiveCountingStats
    configuration_fingerprint: str
    counting_closed: bool
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        _opaque_id(self.source_id, "Counting summary source ID", _SOURCE_ID)
        _opaque_id(self.counting_lifecycle_id, "Counting summary lifecycle ID")
        _opaque_id(self.crossing_lifecycle_id, "Crossing summary lifecycle ID")
        if not isinstance(self.crossing_summary, LiveCrossingRunSummary):
            raise InputDataError("Counting summary requires a live crossing summary.")
        if not isinstance(self.counting_statistics, LiveCountingStats):
            raise InputDataError("Counting summary statistics are invalid.")
        _sha256(self.configuration_fingerprint, "Counting summary fingerprint")
        if not isinstance(self.counting_closed, bool):
            raise InputDataError("Counting summary close state must be boolean.")
        if (
            not isinstance(self.limitations, tuple)
            or not self.limitations
            or len(self.limitations) > 8
            or any(
                not isinstance(item, str) or not item.strip() or len(item) > 256
                for item in self.limitations
            )
        ):
            raise InputDataError("Counting summary limitations must be bounded text.")


__all__ = [
    "CountingDecisionType",
    "DuplicateCountingPolicy",
    "LiveCountingConfiguration",
    "LiveCountingDecision",
    "LiveCountingErrorCategory",
    "LiveCountingHealthState",
    "LiveCountingResult",
    "LiveCountingRunSummary",
    "LiveCountingSnapshot",
    "LiveCountingStats",
    "OperationalCrossingDirection",
    "ReverseCountingPolicy",
    "TemporaryTrackIdentity",
]
