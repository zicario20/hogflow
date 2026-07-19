"""Immutable framework-neutral models for live detector inference."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from re import fullmatch

from hogflow.core import ConfigurationError, InputDataError
from hogflow.models import Detection
from hogflow.streaming.models import SourceType, StreamHealthState

_SHA256_PATTERN = r"[0-9a-f]{64}"
_OPAQUE_ID_PATTERN = r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}"


def _non_negative_integer(value: object, *, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InputDataError(f"{name} must be a non-negative integer.")
    return value


def _non_negative_finite(value: object, *, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or float(value) < 0
    ):
        raise InputDataError(f"{name} must be a finite non-negative number.")
    return float(value)


def _optional_positive(value: object | None, *, name: str) -> float | None:
    if value is None:
        return None
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or float(value) <= 0
    ):
        raise ConfigurationError(f"{name} must be a finite positive number when provided.")
    return float(value)


class DetectionShutdownReason(str, Enum):
    """Bounded terminal reasons for one live detector run."""

    SOURCE_CLOSED = "source_closed"
    MAXIMUM_FRAMES = "maximum_frames"
    MAXIMUM_DURATION = "maximum_duration"
    PREVIEW_REQUESTED = "preview_requested"
    KEYBOARD_INTERRUPT = "keyboard_interrupt"


class PreviewAction(str, Enum):
    """Actions a local preview may request from orchestration."""

    CONTINUE = "continue"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class LiveInferenceConfiguration:
    """Validated scheduling policy for bounded-latency live inference.

    Every-N selection uses the original source sequence number. Target FPS and
    maximum age are optional additional gates. The consumer never sleeps to
    pace acquisition; non-eligible packets are skipped explicitly instead.
    """

    inference_every_n_frames: int = 1
    target_inference_fps: float | None = None
    maximum_frame_age_ms: float | None = None
    latency_sample_capacity: int = 512
    buffer_poll_timeout_seconds: float = 0.1

    def __post_init__(self) -> None:
        if (
            not isinstance(self.inference_every_n_frames, int)
            or isinstance(self.inference_every_n_frames, bool)
            or self.inference_every_n_frames <= 0
        ):
            raise ConfigurationError("inference_every_n_frames must be a positive integer.")
        object.__setattr__(
            self,
            "target_inference_fps",
            _optional_positive(self.target_inference_fps, name="target_inference_fps"),
        )
        object.__setattr__(
            self,
            "maximum_frame_age_ms",
            _optional_positive(self.maximum_frame_age_ms, name="maximum_frame_age_ms"),
        )
        if (
            not isinstance(self.latency_sample_capacity, int)
            or isinstance(self.latency_sample_capacity, bool)
            or self.latency_sample_capacity <= 0
        ):
            raise ConfigurationError("latency_sample_capacity must be a positive integer.")
        timeout = _optional_positive(
            self.buffer_poll_timeout_seconds,
            name="buffer_poll_timeout_seconds",
        )
        object.__setattr__(self, "buffer_poll_timeout_seconds", timeout)


@dataclass(frozen=True, slots=True)
class ModelArtifactMetadata:
    """Sanitized model identity and provenance exposed after detector loading.

    Missing provenance remains ``None`` and must never be inferred. Artifact
    filenames contain no directory. A true ``pig_detection_provenance_complete``
    value means supplied local provenance passed structural checks; it is not
    an accuracy or production-readiness claim.
    """

    model_id: str
    framework: str
    class_mapping: tuple[tuple[int, str], ...]
    artifact_filename: str | None = None
    artifact_fingerprint: str | None = None
    model_version: str | None = None
    expected_input_size: tuple[int, int] | None = None
    training_run_id: str | None = None
    dataset_fingerprint: str | None = None
    evaluation_reference: str | None = None
    pig_detection_provenance_complete: bool = False

    def __post_init__(self) -> None:
        if (
            not isinstance(self.model_id, str)
            or fullmatch(_OPAQUE_ID_PATTERN, self.model_id) is None
        ):
            raise InputDataError("model_id must be a non-sensitive opaque identifier.")
        if not isinstance(self.framework, str) or not self.framework.strip():
            raise InputDataError("Model framework must be non-empty text.")
        if not isinstance(self.class_mapping, tuple):
            raise InputDataError("Model class mapping must be an immutable tuple.")
        class_ids: list[int] = []
        for item in self.class_mapping:
            if (
                not isinstance(item, tuple)
                or len(item) != 2
                or not isinstance(item[0], int)
                or isinstance(item[0], bool)
                or item[0] < 0
                or not isinstance(item[1], str)
                or not item[1].strip()
            ):
                raise InputDataError("Model class mapping entries must be (non-negative ID, name).")
            class_ids.append(item[0])
        if tuple(sorted(self.class_mapping)) != self.class_mapping or len(set(class_ids)) != len(
            class_ids
        ):
            raise InputDataError(
                "Model class mapping must be uniquely and deterministically sorted."
            )
        if self.artifact_filename is not None:
            if (
                not self.artifact_filename
                or "/" in self.artifact_filename
                or "\\" in self.artifact_filename
                or ":" in self.artifact_filename
            ):
                raise InputDataError("Artifact filename must not contain a local path.")
        if (
            self.artifact_fingerprint is not None
            and fullmatch(_SHA256_PATTERN, self.artifact_fingerprint) is None
        ):
            raise InputDataError("Artifact fingerprint must be a SHA-256 hexadecimal digest.")
        if (
            self.dataset_fingerprint is not None
            and fullmatch(_SHA256_PATTERN, self.dataset_fingerprint) is None
        ):
            raise InputDataError("Dataset fingerprint must be a SHA-256 hexadecimal digest.")
        if self.expected_input_size is not None:
            if (
                not isinstance(self.expected_input_size, tuple)
                or len(self.expected_input_size) != 2
                or any(
                    not isinstance(value, int) or isinstance(value, bool) or value <= 0
                    for value in self.expected_input_size
                )
            ):
                raise InputDataError("Expected input size must contain two positive integers.")
        for field_name in ("model_version", "training_run_id", "evaluation_reference"):
            value = getattr(self, field_name)
            if value is not None and (
                not isinstance(value, str) or fullmatch(_OPAQUE_ID_PATTERN, value) is None
            ):
                raise InputDataError(f"{field_name} must be an opaque identifier when provided.")
        if not isinstance(self.pig_detection_provenance_complete, bool):
            raise InputDataError("pig_detection_provenance_complete must be boolean.")


@dataclass(frozen=True, slots=True)
class FrameDetections:
    """Detections for exactly one source frame and one loaded model artifact."""

    source_id: str
    frame_sequence: int
    captured_at: datetime
    inference_started_at: datetime
    inference_completed_at: datetime
    frame_width: int
    frame_height: int
    detections: tuple[Detection, ...]
    model_id: str
    model_version: str | None
    artifact_fingerprint: str | None
    inference_duration_ms: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_id, str)
            or fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", self.source_id) is None
        ):
            raise InputDataError("Detection source ID must be opaque text.")
        _non_negative_integer(self.frame_sequence, name="Frame sequence")
        for name in ("captured_at", "inference_started_at", "inference_completed_at"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise InputDataError(f"{name} must be a timezone-aware datetime.")
        if self.inference_completed_at < self.inference_started_at:
            raise InputDataError("Inference completion cannot precede its start.")
        for name in ("frame_width", "frame_height"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise InputDataError(f"{name} must be a positive integer.")
        if not isinstance(self.detections, tuple) or not all(
            isinstance(item, Detection) for item in self.detections
        ):
            raise InputDataError("Frame detections must be an immutable Detection tuple.")
        for detection in self.detections:
            box = detection.bounding_box
            if (
                box.x_min < 0
                or box.y_min < 0
                or box.x_max > self.frame_width
                or box.y_max > self.frame_height
            ):
                raise InputDataError("Detection boxes must remain within their source frame.")
        if (
            not isinstance(self.model_id, str)
            or fullmatch(_OPAQUE_ID_PATTERN, self.model_id) is None
        ):
            raise InputDataError("Frame detection model ID must be opaque text.")
        if (
            self.artifact_fingerprint is not None
            and fullmatch(_SHA256_PATTERN, self.artifact_fingerprint) is None
        ):
            raise InputDataError("Frame artifact fingerprint must be SHA-256 text.")
        if self.model_version is not None and (
            not isinstance(self.model_version, str)
            or fullmatch(_OPAQUE_ID_PATTERN, self.model_version) is None
        ):
            raise InputDataError("Frame model version must be an opaque identifier.")
        object.__setattr__(
            self,
            "inference_duration_ms",
            _non_negative_finite(self.inference_duration_ms, name="Inference duration"),
        )


@dataclass(frozen=True, slots=True)
class LiveDetectionStats:
    """Bounded aggregate camera and detector telemetry for one live run."""

    frames_acquired: int
    frames_submitted: int
    frames_inferred: int
    frames_skipped: int
    source_frames_dropped: int
    inference_failures: int
    total_detections: int
    preview_failures: int
    average_inference_ms: float
    p50_inference_ms: float
    p95_inference_ms: float
    effective_inference_fps: float
    camera_fps: float | None
    latest_frame_age_ms: float | None
    maximum_frame_age_ms: float

    def __post_init__(self) -> None:
        for name in (
            "frames_acquired",
            "frames_submitted",
            "frames_inferred",
            "frames_skipped",
            "source_frames_dropped",
            "inference_failures",
            "total_detections",
            "preview_failures",
        ):
            _non_negative_integer(getattr(self, name), name=name)
        for name in (
            "average_inference_ms",
            "p50_inference_ms",
            "p95_inference_ms",
            "effective_inference_fps",
            "maximum_frame_age_ms",
        ):
            _non_negative_finite(getattr(self, name), name=name)
        if self.camera_fps is not None:
            _non_negative_finite(self.camera_fps, name="camera_fps")
        if self.latest_frame_age_ms is not None:
            _non_negative_finite(self.latest_frame_age_ms, name="latest_frame_age_ms")
        if self.frames_submitted != (
            self.frames_inferred + self.frames_skipped + self.inference_failures
        ):
            raise InputDataError(
                "Inference accounting requires submitted = inferred + skipped + failures."
            )


@dataclass(frozen=True, slots=True)
class LiveDetectionRunSummary:
    """Sanitized terminal state for one local live detector run."""

    source_id: str
    source_type: SourceType
    source_display_name: str
    detector: ModelArtifactMetadata
    statistics: LiveDetectionStats
    shutdown_reason: DetectionShutdownReason
    final_camera_health: StreamHealthState
    detector_closed: bool
    camera_released: bool

    def __post_init__(self) -> None:
        if (
            not isinstance(self.source_id, str)
            or fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", self.source_id) is None
        ):
            raise InputDataError("Run summary source ID must be opaque text.")
        if not isinstance(self.source_type, SourceType):
            raise InputDataError("Run summary source type must be explicit.")
        if not isinstance(self.source_display_name, str) or not self.source_display_name.strip():
            raise InputDataError("Run summary source display name must be non-empty text.")
        lowered_display_name = self.source_display_name.lower()
        if any(
            token in lowered_display_name
            for token in ("@", "://", "\\", "/", "password", "credential")
        ):
            raise InputDataError("Run summary source display name contains unsafe material.")
        if not isinstance(self.detector, ModelArtifactMetadata):
            raise InputDataError("Run summary detector metadata is invalid.")
        if not isinstance(self.statistics, LiveDetectionStats):
            raise InputDataError("Run summary statistics are invalid.")
        if not isinstance(self.shutdown_reason, DetectionShutdownReason):
            raise InputDataError("Run summary shutdown reason is invalid.")
        if not isinstance(self.final_camera_health, StreamHealthState):
            raise InputDataError("Run summary camera health must be explicit.")
        if not isinstance(self.detector_closed, bool) or not isinstance(self.camera_released, bool):
            raise InputDataError("Run summary resource states must be boolean.")


__all__ = [
    "DetectionShutdownReason",
    "FrameDetections",
    "LiveDetectionRunSummary",
    "LiveDetectionStats",
    "LiveInferenceConfiguration",
    "ModelArtifactMetadata",
    "PreviewAction",
]
