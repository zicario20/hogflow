"""Immutable camera and shared counting-pipeline status projections."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from math import isfinite
from re import fullmatch

from hogflow.core import ConfigurationError
from hogflow.detection import DetectorRuntimeSnapshot
from hogflow.domain import DockId
from hogflow.streaming import SourceType

_OPAQUE_ID = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"


class CameraStatus(str, Enum):
    """Lifecycle state of the one configured source."""

    NOT_CONFIGURED = "not_configured"
    CLOSED = "closed"
    OPENING = "opening"
    RUNNING = "running"
    DISCONNECTED = "disconnected"
    ENDED = "ended"
    FAILED = "failed"


class CountingPipelineStatus(str, Enum):
    """Lifecycle state of the one shared camera-processing worker."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


class PipelineFailureCategory(str, Enum):
    """Bounded error categories safe for presentation snapshots."""

    NONE = "none"
    CONFIGURATION = "configuration"
    SOURCE_OPEN = "source_open"
    SOURCE_READ = "source_read"
    DETECTOR = "detector"
    TRACKER = "tracker"
    CROSSING = "crossing"
    STALE_EVIDENCE = "stale_evidence"
    LIFECYCLE = "lifecycle"
    SHUTDOWN = "shutdown"
    INTERNAL = "internal"


@dataclass(frozen=True, slots=True)
class CameraRecoveryConfiguration:
    """Bounded reopen policy for the one live USB source.

    Recovery is never applied to normal local-file exhaustion. The maximum is
    per pipeline run, so a broken source cannot create an endless reopen loop.
    """

    enabled: bool = True
    max_reopen_attempts: int = 3
    temporary_failures_before_reopen: int = 3
    retry_delay_seconds: float = 0.25

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ConfigurationError("Camera recovery enabled state must be boolean.")
        for value, label in (
            (self.max_reopen_attempts, "maximum reopen attempts"),
            (
                self.temporary_failures_before_reopen,
                "temporary failures before reopen",
            ),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ConfigurationError(f"Camera recovery {label} must be non-negative.")
        if self.enabled and self.temporary_failures_before_reopen == 0:
            raise ConfigurationError(
                "Enabled camera recovery requires at least one temporary failure."
            )
        if self.enabled and self.max_reopen_attempts == 0:
            raise ConfigurationError(
                "Enabled camera recovery requires at least one reopen attempt."
            )
        if (
            not isinstance(self.retry_delay_seconds, (int, float))
            or isinstance(self.retry_delay_seconds, bool)
            or not isfinite(self.retry_delay_seconds)
            or float(self.retry_delay_seconds) < 0
        ):
            raise ConfigurationError("Camera recovery retry delay must be finite and non-negative.")
        object.__setattr__(self, "retry_delay_seconds", float(self.retry_delay_seconds))


@dataclass(frozen=True, slots=True)
class ActiveCountingBinding:
    """Immutable ownership needed to route one crossing result safely."""

    dock_id: DockId
    source_id: str
    crossing_lifecycle_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.dock_id, DockId):
            raise ValueError("Camera counting binding requires a supported dock.")
        for value, label in (
            (self.source_id, "source ID"),
            (self.crossing_lifecycle_id, "crossing lifecycle ID"),
        ):
            if not isinstance(value, str) or fullmatch(_OPAQUE_ID, value) is None:
                raise ValueError(f"Camera counting binding {label} must be opaque text.")


@dataclass(frozen=True, slots=True)
class CameraSnapshot:
    """Sanitized source state without paths or framework objects."""

    source_id: str | None
    source_type: SourceType | None
    display_name: str
    status: CameraStatus
    last_frame_index: int | None
    frames_acquired: int
    last_successful_frame_at: datetime | None
    source_exhausted: bool
    failure_category: PipelineFailureCategory
    failure_message: str | None

    def __post_init__(self) -> None:
        if self.source_id is not None and (
            not isinstance(self.source_id, str) or fullmatch(_OPAQUE_ID, self.source_id) is None
        ):
            raise ValueError("Camera snapshot source ID must be opaque text.")
        if self.source_type is not None and not isinstance(self.source_type, SourceType):
            raise ValueError("Camera snapshot source type must be explicit.")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise ValueError("Camera snapshot display name must be non-empty text.")
        if not isinstance(self.status, CameraStatus):
            raise ValueError("Camera snapshot status must be explicit.")
        if self.last_frame_index is not None and (
            not isinstance(self.last_frame_index, int)
            or isinstance(self.last_frame_index, bool)
            or self.last_frame_index < 0
        ):
            raise ValueError("Camera snapshot frame index must be non-negative.")
        if (
            not isinstance(self.frames_acquired, int)
            or isinstance(self.frames_acquired, bool)
            or self.frames_acquired < 0
        ):
            raise ValueError("Camera snapshot acquired frames must be non-negative.")
        if self.last_successful_frame_at is not None and (
            not isinstance(self.last_successful_frame_at, datetime)
            or self.last_successful_frame_at.tzinfo is None
        ):
            raise ValueError("Camera snapshot frame timestamp must be timezone-aware.")
        if not isinstance(self.source_exhausted, bool):
            raise ValueError("Camera snapshot exhaustion state must be boolean.")
        if not isinstance(self.failure_category, PipelineFailureCategory):
            raise ValueError("Camera snapshot failure category must be explicit.")
        _validate_failure(self.failure_category, self.failure_message)


@dataclass(frozen=True, slots=True)
class CountingPipelineSnapshot:
    """Bounded status of the one worker shared by all four docks."""

    status: CountingPipelineStatus
    camera: CameraSnapshot
    frames_processed: int
    temporary_processing_failures: int
    stale_results_rejected: int
    active_crossing_lifecycle_id: str | None
    worker_alive: bool
    failure_category: PipelineFailureCategory
    failure_message: str | None
    started_at: datetime | None
    stopped_at: datetime | None
    effective_fps: float = 0.0
    recovery_attempts: int = 0
    recovery_successes: int = 0
    last_processed_frame_index: int | None = None
    camera_failures: int = 0
    detector_failures: int = 0
    tracker_failures: int = 0
    crossing_failures: int = 0
    frames_dropped: int = 0
    processing_samples: int = 0
    average_processing_latency_ms: float = 0.0
    maximum_processing_latency_ms: float = 0.0
    consecutive_camera_failures: int = 0
    consecutive_detector_failures: int = 0
    detector: DetectorRuntimeSnapshot = field(default_factory=DetectorRuntimeSnapshot.empty)

    def __post_init__(self) -> None:
        if not isinstance(self.status, CountingPipelineStatus):
            raise ValueError("Counting pipeline status must be explicit.")
        if not isinstance(self.camera, CameraSnapshot):
            raise ValueError("Counting pipeline snapshot requires a camera snapshot.")
        if not isinstance(self.detector, DetectorRuntimeSnapshot):
            raise ValueError("Counting pipeline snapshot requires detector diagnostics.")
        for value, label in (
            (self.frames_processed, "processed frames"),
            (self.temporary_processing_failures, "temporary processing failures"),
            (self.stale_results_rejected, "stale results"),
            (self.recovery_attempts, "recovery attempts"),
            (self.recovery_successes, "recovery successes"),
            (self.camera_failures, "camera failures"),
            (self.detector_failures, "detector failures"),
            (self.tracker_failures, "tracker failures"),
            (self.crossing_failures, "crossing failures"),
            (self.frames_dropped, "dropped frames"),
            (self.processing_samples, "processing samples"),
            (self.consecutive_camera_failures, "consecutive camera failures"),
            (self.consecutive_detector_failures, "consecutive detector failures"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"Counting pipeline {label} must be non-negative.")
        if self.recovery_successes > self.recovery_attempts:
            raise ValueError("Pipeline recovery successes cannot exceed attempts.")
        if self.last_processed_frame_index is not None and (
            not isinstance(self.last_processed_frame_index, int)
            or isinstance(self.last_processed_frame_index, bool)
            or self.last_processed_frame_index < 0
        ):
            raise ValueError("Last processed frame index must be non-negative.")
        if self.last_processed_frame_index is not None and (
            self.camera.last_frame_index is None
            or self.last_processed_frame_index > self.camera.last_frame_index
        ):
            raise ValueError("Last processed frame cannot exceed the acquired frame sequence.")
        if (
            not isinstance(self.effective_fps, (int, float))
            or isinstance(self.effective_fps, bool)
            or not isfinite(self.effective_fps)
            or float(self.effective_fps) < 0
        ):
            raise ValueError("Counting pipeline FPS must be finite and non-negative.")
        object.__setattr__(self, "effective_fps", float(self.effective_fps))
        for name in (
            "average_processing_latency_ms",
            "maximum_processing_latency_ms",
        ):
            value = getattr(self, name)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not isfinite(value)
                or float(value) < 0
            ):
                raise ValueError("Counting pipeline latency must be finite and non-negative.")
            object.__setattr__(self, name, float(value))
        if self.processing_samples == 0 and (
            self.average_processing_latency_ms != 0.0 or self.maximum_processing_latency_ms != 0.0
        ):
            raise ValueError("Pipeline latency requires at least one processing sample.")
        if self.maximum_processing_latency_ms < self.average_processing_latency_ms:
            raise ValueError("Maximum pipeline latency cannot be below its average.")
        if self.active_crossing_lifecycle_id is not None and (
            not isinstance(self.active_crossing_lifecycle_id, str)
            or fullmatch(_OPAQUE_ID, self.active_crossing_lifecycle_id) is None
        ):
            raise ValueError("Active crossing lifecycle ID must be opaque text.")
        if not isinstance(self.worker_alive, bool):
            raise ValueError("Worker state must be boolean.")
        if not isinstance(self.failure_category, PipelineFailureCategory):
            raise ValueError("Pipeline failure category must be explicit.")
        _validate_failure(self.failure_category, self.failure_message)
        for value, label in ((self.started_at, "start"), (self.stopped_at, "stop")):
            if value is not None and (not isinstance(value, datetime) or value.tzinfo is None):
                raise ValueError(f"Pipeline {label} time must be timezone-aware.")
        if self.started_at is not None and self.stopped_at is not None:
            if self.stopped_at < self.started_at:
                raise ValueError("Pipeline stop time cannot precede start time.")


def _validate_failure(
    category: PipelineFailureCategory,
    message: str | None,
) -> None:
    if category is PipelineFailureCategory.NONE:
        if message is not None:
            raise ValueError("A healthy snapshot cannot contain a failure message.")
        return
    if not isinstance(message, str) or not message.strip() or len(message) > 256:
        raise ValueError("A failed snapshot requires a bounded sanitized message.")
    forbidden = ("\\", "://", "password", "credential", "traceback")
    if any(token in message.lower() for token in forbidden):
        raise ValueError("Snapshot failure message contains unsafe details.")


__all__ = [
    "ActiveCountingBinding",
    "CameraRecoveryConfiguration",
    "CameraSnapshot",
    "CameraStatus",
    "CountingPipelineSnapshot",
    "CountingPipelineStatus",
    "PipelineFailureCategory",
]
