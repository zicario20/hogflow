"""Immutable health, heartbeat, diagnostics, and configuration models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite

from hogflow.runtime.errors import ProductionRuntimeConfigurationError


def _non_negative_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{label} must be a non-negative integer.")
    return value


def _positive_int(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{label} must be a positive integer.")
    return value


def _non_negative_float(value: object, label: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or float(value) < 0
    ):
        raise ValueError(f"{label} must be finite and non-negative.")
    return float(value)


def _positive_float(value: object, label: str) -> float:
    result = _non_negative_float(value, label)
    if result <= 0:
        raise ValueError(f"{label} must be positive.")
    return result


def _aware(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware.")
    return value


class RuntimeHealthState(str, Enum):
    """Overall state of the supervised local runtime."""

    CREATED = "created"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"


class RuntimeComponent(str, Enum):
    """Components observed without exposing implementation objects."""

    WORKER = "worker"
    CAMERA = "camera"
    PIPELINE = "pipeline"
    PREVIEW = "preview"
    COUNTER = "counter"
    LANE = "lane"


class ComponentHealthState(str, Enum):
    """Current bounded state of one observed component."""

    IDLE = "idle"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    STOPPED = "stopped"


class RuntimeIssueDisposition(str, Enum):
    """Whether controlled restart can safely address one issue."""

    RECOVERABLE = "recoverable"
    FATAL = "fatal"


class RuntimeIssueCategory(str, Enum):
    """Finite failure/warning categories retained by the supervisor."""

    PIPELINE_STALLED = "pipeline_stalled"
    WORKER_DEAD = "worker_dead"
    STALE_FRAME = "stale_frame"
    CAMERA_FAILURE = "camera_failure"
    REPEATED_CAMERA_FAILURES = "repeated_camera_failures"
    DETECTOR_FAILURE = "detector_failure"
    REPEATED_DETECTOR_FAILURES = "repeated_detector_failures"
    TRACKER_FAILURE = "tracker_failure"
    CROSSING_FAILURE = "crossing_failure"
    PIPELINE_FAILURE = "pipeline_failure"
    PREVIEW_FAILURE = "preview_failure"
    LANE_FAILURE = "lane_failure"


class RuntimeWorkerState(str, Enum):
    """Worker state projected independently from the camera framework."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    DEAD = "dead"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ProductionRuntimeConfiguration:
    """Validated engineering thresholds for local long-running supervision.

    These defaults are not production-certified values. They must be tuned and
    validated for the selected source, detector, hardware, and shift workflow.
    """

    heartbeat_interval_seconds: float = 5.0
    stale_frame_after_seconds: float = 15.0
    stalled_pipeline_after_seconds: float = 30.0
    repeated_camera_failure_threshold: int = 3
    repeated_detector_failure_threshold: int = 3
    maximum_manual_restarts: int = 3
    warning_capacity: int = 32
    require_idle_lane_for_restart: bool = True
    schema_version: str = "1"

    def __post_init__(self) -> None:
        try:
            for name in (
                "heartbeat_interval_seconds",
                "stale_frame_after_seconds",
                "stalled_pipeline_after_seconds",
            ):
                object.__setattr__(self, name, _positive_float(getattr(self, name), name))
            for name in (
                "repeated_camera_failure_threshold",
                "repeated_detector_failure_threshold",
                "maximum_manual_restarts",
                "warning_capacity",
            ):
                _positive_int(getattr(self, name), name)
        except ValueError as exc:
            raise ProductionRuntimeConfigurationError(str(exc)) from exc
        if not isinstance(self.require_idle_lane_for_restart, bool):
            raise ProductionRuntimeConfigurationError(
                "Runtime restart lane policy must be boolean."
            )
        if self.schema_version != "1":
            raise ProductionRuntimeConfigurationError(
                "Unsupported production runtime configuration schema version."
            )

    @property
    def fingerprint(self) -> str:
        payload = {
            "heartbeat_interval_seconds": self.heartbeat_interval_seconds,
            "maximum_manual_restarts": self.maximum_manual_restarts,
            "repeated_camera_failure_threshold": self.repeated_camera_failure_threshold,
            "repeated_detector_failure_threshold": self.repeated_detector_failure_threshold,
            "require_idle_lane_for_restart": self.require_idle_lane_for_restart,
            "schema_version": self.schema_version,
            "stale_frame_after_seconds": self.stale_frame_after_seconds,
            "stalled_pipeline_after_seconds": self.stalled_pipeline_after_seconds,
            "warning_capacity": self.warning_capacity,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ComponentHealth:
    """One immutable component health projection."""

    component: RuntimeComponent
    state: ComponentHealthState

    def __post_init__(self) -> None:
        if not isinstance(self.component, RuntimeComponent):
            raise ValueError("Runtime component must be explicit.")
        if not isinstance(self.state, ComponentHealthState):
            raise ValueError("Runtime component health must be explicit.")


@dataclass(frozen=True, slots=True)
class RuntimeIssue:
    """Sanitized recoverable or fatal issue without exception details."""

    category: RuntimeIssueCategory
    component: RuntimeComponent
    disposition: RuntimeIssueDisposition
    message: str
    observed_at: datetime
    occurrences: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.category, RuntimeIssueCategory):
            raise ValueError("Runtime issue category must be explicit.")
        if not isinstance(self.component, RuntimeComponent):
            raise ValueError("Runtime issue component must be explicit.")
        if not isinstance(self.disposition, RuntimeIssueDisposition):
            raise ValueError("Runtime issue disposition must be explicit.")
        if not isinstance(self.message, str) or not self.message.strip() or len(self.message) > 256:
            raise ValueError("Runtime issue message must be bounded text.")
        forbidden = ("\\", "://", "password", "credential", "traceback")
        if any(token in self.message.lower() for token in forbidden):
            raise ValueError("Runtime issue message contains unsafe details.")
        _aware(self.observed_at, "Runtime issue time")
        _positive_int(self.occurrences, "Runtime issue occurrences")


@dataclass(frozen=True, slots=True)
class ProcessMemorySnapshot:
    """Bounded process-memory sample with no allocation history."""

    captured_at: datetime
    available: bool
    resident_bytes: int
    peak_resident_bytes: int

    def __post_init__(self) -> None:
        _aware(self.captured_at, "Memory capture time")
        if not isinstance(self.available, bool):
            raise ValueError("Memory availability must be boolean.")
        _non_negative_int(self.resident_bytes, "Resident memory")
        _non_negative_int(self.peak_resident_bytes, "Peak resident memory")
        if self.peak_resident_bytes < self.resident_bytes:
            raise ValueError("Peak resident memory cannot be below current resident memory.")
        if not self.available and (self.resident_bytes or self.peak_resident_bytes):
            raise ValueError("Unavailable memory samples must use zero values.")


@dataclass(frozen=True, slots=True)
class RuntimeDiagnosticsSnapshot:
    """Constant-memory aggregate diagnostics for the process lifetime."""

    heartbeat_count: int
    fps_samples: int
    average_fps: float
    minimum_fps: float
    maximum_fps: float
    processing_samples: int
    average_processing_latency_ms: float
    maximum_processing_latency_ms: float
    camera_reconnect_count: int
    camera_restart_count: int
    pipeline_restart_count: int
    worker_restart_count: int
    preview_restart_count: int
    frames_dropped: int
    camera_failures: int
    detector_failures: int
    tracker_failures: int
    crossing_failures: int
    preview_failures: int
    stale_evidence_rejected: int
    warnings_emitted: int
    recent_warnings: tuple[RuntimeIssue, ...]
    warning_capacity: int

    def __post_init__(self) -> None:
        for name in (
            "heartbeat_count",
            "fps_samples",
            "processing_samples",
            "camera_reconnect_count",
            "camera_restart_count",
            "pipeline_restart_count",
            "worker_restart_count",
            "preview_restart_count",
            "frames_dropped",
            "camera_failures",
            "detector_failures",
            "tracker_failures",
            "crossing_failures",
            "preview_failures",
            "stale_evidence_rejected",
            "warnings_emitted",
        ):
            _non_negative_int(getattr(self, name), name)
        for name in (
            "average_fps",
            "minimum_fps",
            "maximum_fps",
            "average_processing_latency_ms",
            "maximum_processing_latency_ms",
        ):
            object.__setattr__(self, name, _non_negative_float(getattr(self, name), name))
        _positive_int(self.warning_capacity, "Warning capacity")
        if len(self.recent_warnings) > self.warning_capacity or not all(
            isinstance(item, RuntimeIssue) for item in self.recent_warnings
        ):
            raise ValueError("Runtime warning history must be an immutable bounded tuple.")
        if self.fps_samples == 0 and any(
            value != 0.0 for value in (self.average_fps, self.minimum_fps, self.maximum_fps)
        ):
            raise ValueError("FPS aggregates require at least one sample.")
        if not self.minimum_fps <= self.average_fps <= self.maximum_fps:
            raise ValueError("FPS aggregates are inconsistent.")
        if self.processing_samples == 0 and (
            self.average_processing_latency_ms or self.maximum_processing_latency_ms
        ):
            raise ValueError("Latency aggregates require at least one sample.")
        if self.maximum_processing_latency_ms < self.average_processing_latency_ms:
            raise ValueError("Maximum processing latency cannot be below its average.")


@dataclass(frozen=True, slots=True)
class RuntimeHeartbeat:
    """One immutable heartbeat generated without retaining prior heartbeats."""

    sequence: int
    generated_at: datetime
    uptime_seconds: float
    health_state: RuntimeHealthState
    components: tuple[ComponentHealth, ...]
    current_issues: tuple[RuntimeIssue, ...]
    last_processed_frame: int | None
    last_successful_count: int | None
    last_successful_count_at: datetime | None
    current_fps: float
    memory: ProcessMemorySnapshot
    pipeline_queue_size: int
    pipeline_queue_capacity: int
    preview_queue_size: int
    preview_queue_capacity: int
    worker_state: RuntimeWorkerState
    diagnostics: RuntimeDiagnosticsSnapshot
    configuration_fingerprint: str

    def __post_init__(self) -> None:
        _positive_int(self.sequence, "Heartbeat sequence")
        _aware(self.generated_at, "Heartbeat generation time")
        object.__setattr__(
            self,
            "uptime_seconds",
            _non_negative_float(self.uptime_seconds, "Runtime uptime"),
        )
        if not isinstance(self.health_state, RuntimeHealthState):
            raise ValueError("Runtime heartbeat health must be explicit.")
        expected_components = tuple(RuntimeComponent)
        if tuple(item.component for item in self.components) != expected_components:
            raise ValueError("Heartbeat must contain every runtime component in stable order.")
        if not all(isinstance(item, RuntimeIssue) for item in self.current_issues):
            raise ValueError("Heartbeat issues must be immutable runtime issues.")
        if self.last_processed_frame is not None:
            _non_negative_int(self.last_processed_frame, "Last processed frame")
        if self.last_successful_count is not None:
            _positive_int(self.last_successful_count, "Last successful count")
        if (self.last_successful_count is None) != (self.last_successful_count_at is None):
            raise ValueError("Last count value and time must be present together.")
        if self.last_successful_count_at is not None:
            _aware(self.last_successful_count_at, "Last successful count time")
        object.__setattr__(self, "current_fps", _non_negative_float(self.current_fps, "FPS"))
        if not isinstance(self.memory, ProcessMemorySnapshot):
            raise ValueError("Heartbeat requires a process memory snapshot.")
        for size, capacity, label in (
            (self.pipeline_queue_size, self.pipeline_queue_capacity, "Pipeline queue"),
            (self.preview_queue_size, self.preview_queue_capacity, "Preview queue"),
        ):
            _non_negative_int(size, f"{label} size")
            _non_negative_int(capacity, f"{label} capacity")
            if size > capacity:
                raise ValueError(f"{label} size cannot exceed capacity.")
        if not isinstance(self.worker_state, RuntimeWorkerState):
            raise ValueError("Heartbeat worker state must be explicit.")
        if not isinstance(self.diagnostics, RuntimeDiagnosticsSnapshot):
            raise ValueError("Heartbeat diagnostics are invalid.")
        if (
            not isinstance(self.configuration_fingerprint, str)
            or len(self.configuration_fingerprint) != 64
            or any(
                character not in "0123456789abcdef" for character in self.configuration_fingerprint
            )
        ):
            raise ValueError("Runtime configuration fingerprint must be SHA-256 text.")


__all__ = [
    "ComponentHealth",
    "ComponentHealthState",
    "ProcessMemorySnapshot",
    "ProductionRuntimeConfiguration",
    "RuntimeComponent",
    "RuntimeDiagnosticsSnapshot",
    "RuntimeHealthState",
    "RuntimeHeartbeat",
    "RuntimeIssue",
    "RuntimeIssueCategory",
    "RuntimeIssueDisposition",
    "RuntimeWorkerState",
]
