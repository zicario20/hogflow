"""Immutable camera and shared counting-pipeline status projections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from re import fullmatch

from hogflow.domain import DockId
from hogflow.streaming import SourceType

_OPAQUE_ID = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"


class CameraStatus(str, Enum):
    """Lifecycle state of the one configured source."""

    NOT_CONFIGURED = "not_configured"
    CLOSED = "closed"
    OPENING = "opening"
    RUNNING = "running"
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

    def __post_init__(self) -> None:
        if not isinstance(self.status, CountingPipelineStatus):
            raise ValueError("Counting pipeline status must be explicit.")
        if not isinstance(self.camera, CameraSnapshot):
            raise ValueError("Counting pipeline snapshot requires a camera snapshot.")
        for value, label in (
            (self.frames_processed, "processed frames"),
            (self.temporary_processing_failures, "temporary processing failures"),
            (self.stale_results_rejected, "stale results"),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"Counting pipeline {label} must be non-negative.")
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
    "CameraSnapshot",
    "CameraStatus",
    "CountingPipelineSnapshot",
    "CountingPipelineStatus",
    "PipelineFailureCategory",
]
