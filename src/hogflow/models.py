"""Framework-independent immutable data models shared by HogFlow contracts."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from hogflow.core import InputDataError

_RGB_CHANNEL_COUNT = 3


def _is_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_number(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False


@dataclass(frozen=True, slots=True)
class Frame:
    """One immutable RGB video frame exchanged across contract boundaries.

    ``pixels`` contains row-major, packed, eight-bit RGB data. The payload has
    exactly ``width * height * 3`` bytes and never contains a framework-owned
    image object. ``frame_index`` identifies source order, while the optional
    timestamp describes seconds from the source origin when known.
    """

    frame_index: int
    width: int
    height: int
    pixels: bytes
    timestamp_seconds: float | None = None

    def __post_init__(self) -> None:
        if not _is_integer(self.frame_index) or self.frame_index < 0:
            raise InputDataError("Frame index must be a non-negative integer.")
        if not _is_integer(self.width) or self.width <= 0:
            raise InputDataError("Frame width must be a positive integer.")
        if not _is_integer(self.height) or self.height <= 0:
            raise InputDataError("Frame height must be a positive integer.")
        if not isinstance(self.pixels, bytes):
            raise InputDataError("Frame pixels must be immutable bytes in packed RGB order.")
        expected_size = self.width * self.height * _RGB_CHANNEL_COUNT
        if len(self.pixels) != expected_size:
            raise InputDataError(f"Frame pixel payload must contain exactly {expected_size} bytes.")
        if self.timestamp_seconds is not None and (
            not _is_finite_number(self.timestamp_seconds) or self.timestamp_seconds < 0
        ):
            raise InputDataError("Frame timestamp must be a finite, non-negative number.")


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """An immutable axis-aligned bounding box in frame-coordinate units.

    All coordinates are finite. ``x_max`` and ``y_max`` must exceed their
    corresponding minima so the box always describes positive area.
    """

    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def __post_init__(self) -> None:
        coordinates = (self.x_min, self.y_min, self.x_max, self.y_max)
        if not all(_is_finite_number(coordinate) for coordinate in coordinates):
            raise InputDataError("Bounding-box coordinates must be finite numbers.")
        if self.x_min >= self.x_max or self.y_min >= self.y_max:
            raise InputDataError("Bounding box must have positive width and height.")


@dataclass(frozen=True, slots=True)
class Detection:
    """One immutable detector result expressed without framework-specific data.

    A detection combines a bounding box, confidence from zero through one, and
    non-negative detector class identity. It contains no tracking or counting
    state.
    """

    bounding_box: BoundingBox
    confidence: float
    class_id: int
    class_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.bounding_box, BoundingBox):
            raise InputDataError("Detection bounding_box must be a BoundingBox.")
        if not _is_finite_number(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise InputDataError("Detection confidence must be between 0 and 1.")
        if not _is_integer(self.class_id) or self.class_id < 0:
            raise InputDataError("Detection class_id must be a non-negative integer.")
        if not isinstance(self.class_name, str) or not self.class_name.strip():
            raise InputDataError("Detection class_name must be a non-empty string.")


@dataclass(frozen=True, slots=True)
class Track:
    """One immutable tracked detection with an implementation-scoped identity.

    ``tracker_id`` is meaningful only for the lifetime defined by a tracker
    implementation. It is not a biological, business, database, count-order,
    or session identity.
    """

    tracker_id: int
    detection: Detection

    def __post_init__(self) -> None:
        if not _is_integer(self.tracker_id) or self.tracker_id < 0:
            raise InputDataError("Track tracker_id must be a non-negative integer.")
        if not isinstance(self.detection, Detection):
            raise InputDataError("Track detection must be a Detection.")


__all__ = ["BoundingBox", "Detection", "Frame", "Track"]
