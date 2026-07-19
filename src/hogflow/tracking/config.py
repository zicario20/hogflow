"""Immutable configuration for live tracker adapters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from math import isfinite

from hogflow.core import ConfigurationError


def _probability(value: object, name: str) -> float:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ConfigurationError(f"{name} must be a finite number from 0 through 1.")
    return float(value)


@dataclass(frozen=True, slots=True)
class ByteTrackConfiguration:
    """Configuration supported by Supervision 0.29.1 ``ByteTrack``.

    Defaults mirror the installed framework's engineering defaults. They have
    not been validated for pigs or a production camera environment.
    """

    track_activation_threshold: float = 0.25
    lost_track_buffer: int = 30
    minimum_matching_threshold: float = 0.8
    frame_rate: float = 30.0
    minimum_consecutive_frames: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "track_activation_threshold",
            _probability(self.track_activation_threshold, "track_activation_threshold"),
        )
        object.__setattr__(
            self,
            "minimum_matching_threshold",
            _probability(self.minimum_matching_threshold, "minimum_matching_threshold"),
        )
        if (
            not isinstance(self.lost_track_buffer, int)
            or isinstance(self.lost_track_buffer, bool)
            or self.lost_track_buffer < 0
        ):
            raise ConfigurationError("lost_track_buffer must be a non-negative integer.")
        if (
            not isinstance(self.frame_rate, (int, float))
            or isinstance(self.frame_rate, bool)
            or not isfinite(self.frame_rate)
            or float(self.frame_rate) <= 0
        ):
            raise ConfigurationError("frame_rate must be a finite positive number.")
        object.__setattr__(self, "frame_rate", float(self.frame_rate))
        if (
            not isinstance(self.minimum_consecutive_frames, int)
            or isinstance(self.minimum_consecutive_frames, bool)
            or self.minimum_consecutive_frames <= 0
        ):
            raise ConfigurationError("minimum_consecutive_frames must be a positive integer.")


def byte_track_configuration_fingerprint(configuration: ByteTrackConfiguration) -> str:
    """Return a deterministic SHA-256 fingerprint without private runtime data."""

    if not isinstance(configuration, ByteTrackConfiguration):
        raise ConfigurationError("ByteTrack fingerprinting requires ByteTrackConfiguration.")
    payload = json.dumps(asdict(configuration), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = ["ByteTrackConfiguration", "byte_track_configuration_fingerprint"]
