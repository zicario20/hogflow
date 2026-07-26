"""Immutable framework-neutral models for the one-slot operator preview."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from re import fullmatch

from hogflow.core import ConfigurationError, InputDataError
from hogflow.counting import (
    LineSide,
    LiveCrossingDirection,
    NormalizedLine,
    NormalizedPoint,
)

_SOURCE_ID = r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}"


def _non_negative_integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise InputDataError(f"{label} must be a non-negative integer.")
    return value


def _unit_coordinate(value: object, label: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or not 0.0 <= float(value) <= 1.0
    ):
        raise InputDataError(f"{label} must be finite from 0 through 1.")
    return float(value)


class PreviewHealthState(str, Enum):
    """Bounded visual-channel health independent from counting health."""

    DISABLED = "disabled"
    WAITING = "waiting"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    FAILED = "failed"
    CLOSED = "closed"


class PreviewFailureCategory(str, Enum):
    """Sanitized failure categories for optional visual diagnostics."""

    NONE = "none"
    PUBLICATION = "publication"
    RENDERING = "rendering"


@dataclass(frozen=True, slots=True)
class PreviewConfiguration:
    """Small visual-channel configuration.

    The channel remains a single replaceable slot regardless of settings.
    """

    enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ConfigurationError("Preview enabled state must be boolean.")


@dataclass(frozen=True, slots=True)
class PreviewTrack:
    """One visible temporary track rendered over the current frame."""

    tracker_id: int
    class_id: int
    class_name: str
    confidence: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    anchor: NormalizedPoint
    side: LineSide

    def __post_init__(self) -> None:
        _non_negative_integer(self.tracker_id, "Preview tracker ID")
        _non_negative_integer(self.class_id, "Preview class ID")
        if not isinstance(self.class_name, str) or not self.class_name.strip():
            raise InputDataError("Preview class name must be non-empty text.")
        if (
            not isinstance(self.confidence, (int, float))
            or isinstance(self.confidence, bool)
            or not isfinite(self.confidence)
            or not 0.0 <= float(self.confidence) <= 1.0
        ):
            raise InputDataError("Preview confidence must be finite from 0 through 1.")
        object.__setattr__(self, "confidence", float(self.confidence))
        for name in ("x_min", "y_min", "x_max", "y_max"):
            object.__setattr__(self, name, _unit_coordinate(getattr(self, name), name))
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise InputDataError("Preview track box must have positive normalized area.")
        if not isinstance(self.anchor, NormalizedPoint):
            raise InputDataError("Preview track anchor must be normalized.")
        if not isinstance(self.side, LineSide):
            raise InputDataError("Preview track side must be explicit.")


@dataclass(frozen=True, slots=True)
class PreviewCrossing:
    """One current-frame directional crossing annotation."""

    tracker_id: int
    direction: LiveCrossingDirection

    def __post_init__(self) -> None:
        _non_negative_integer(self.tracker_id, "Preview crossing tracker ID")
        if not isinstance(self.direction, LiveCrossingDirection):
            raise InputDataError("Preview crossing direction must be explicit.")


@dataclass(frozen=True, slots=True, repr=False)
class PreviewFrame:
    """One immutable RGB frame plus current diagnostic overlays.

    This value contains no business snapshot, count, dock ownership, or mutable
    framework object. Its RGB bytes are local and ephemeral.
    """

    source_id: str
    frame_sequence: int
    captured_at: datetime
    frame_width: int
    frame_height: int
    rgb24: bytes
    tracks: tuple[PreviewTrack, ...]
    line: NormalizedLine
    crossings: tuple[PreviewCrossing, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.source_id, str) or fullmatch(_SOURCE_ID, self.source_id) is None:
            raise InputDataError("Preview source ID must be opaque text.")
        _non_negative_integer(self.frame_sequence, "Preview frame sequence")
        if not isinstance(self.captured_at, datetime) or self.captured_at.tzinfo is None:
            raise InputDataError("Preview capture time must be timezone-aware.")
        if (
            not isinstance(self.frame_width, int)
            or isinstance(self.frame_width, bool)
            or self.frame_width <= 0
            or not isinstance(self.frame_height, int)
            or isinstance(self.frame_height, bool)
            or self.frame_height <= 0
        ):
            raise InputDataError("Preview frame dimensions must be positive integers.")
        if not isinstance(self.rgb24, bytes) or len(self.rgb24) != (
            self.frame_width * self.frame_height * 3
        ):
            raise InputDataError("Preview frame must contain packed immutable RGB24 bytes.")
        if not isinstance(self.tracks, tuple) or not all(
            isinstance(item, PreviewTrack) for item in self.tracks
        ):
            raise InputDataError("Preview tracks must be an immutable tuple.")
        if not isinstance(self.line, NormalizedLine):
            raise InputDataError("Preview line must be normalized.")
        if not isinstance(self.crossings, tuple) or not all(
            isinstance(item, PreviewCrossing) for item in self.crossings
        ):
            raise InputDataError("Preview crossings must be an immutable tuple.")

    def __repr__(self) -> str:
        return (
            "PreviewFrame("
            f"source_id={self.source_id!r}, frame_sequence={self.frame_sequence}, "
            f"frame_width={self.frame_width}, frame_height={self.frame_height}, "
            "rgb24=<ephemeral>, "
            f"tracks={len(self.tracks)}, crossings={len(self.crossings)})"
        )


@dataclass(frozen=True, slots=True)
class PreviewSnapshot:
    """Bounded one-slot preview telemetry without a frame payload."""

    enabled: bool
    health_state: PreviewHealthState
    frame_available: bool
    frames_published: int
    frames_replaced: int
    frames_consumed: int
    publication_failures: int
    render_failures: int
    effective_preview_fps: float
    last_frame_sequence: int | None
    failure_category: PreviewFailureCategory
    failure_message: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise InputDataError("Preview snapshot enabled state must be boolean.")
        if not isinstance(self.health_state, PreviewHealthState):
            raise InputDataError("Preview health state must be explicit.")
        if not isinstance(self.frame_available, bool):
            raise InputDataError("Preview availability must be boolean.")
        for name in (
            "frames_published",
            "frames_replaced",
            "frames_consumed",
            "publication_failures",
            "render_failures",
        ):
            _non_negative_integer(getattr(self, name), name)
        if (
            not isinstance(self.effective_preview_fps, (int, float))
            or isinstance(self.effective_preview_fps, bool)
            or not isfinite(self.effective_preview_fps)
            or float(self.effective_preview_fps) < 0
        ):
            raise InputDataError("Preview FPS must be finite and non-negative.")
        if self.last_frame_sequence is not None:
            _non_negative_integer(self.last_frame_sequence, "Last preview frame sequence")
        if not isinstance(self.failure_category, PreviewFailureCategory):
            raise InputDataError("Preview failure category must be explicit.")
        _validate_failure(self.failure_category, self.failure_message)


def _validate_failure(
    category: PreviewFailureCategory,
    message: str | None,
) -> None:
    if category is PreviewFailureCategory.NONE:
        if message is not None:
            raise InputDataError("Healthy preview state cannot contain an error message.")
        return
    if not isinstance(message, str) or not message.strip() or len(message) > 256:
        raise InputDataError("Preview failure requires one bounded message.")
    forbidden = ("\\", "://", "password", "credential", "traceback", "opencv", "cv2")
    if any(token in message.lower() for token in forbidden):
        raise InputDataError("Preview failure message contains unsafe implementation details.")


__all__ = [
    "PreviewConfiguration",
    "PreviewCrossing",
    "PreviewFailureCategory",
    "PreviewFrame",
    "PreviewHealthState",
    "PreviewSnapshot",
    "PreviewTrack",
]
