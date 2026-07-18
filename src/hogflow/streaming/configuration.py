"""Immutable configuration for live sources, buffering, and reconnection."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from re import fullmatch

from hogflow.core import ConfigurationError
from hogflow.streaming.models import OverflowPolicy, SourceType, StreamIdentity
from hogflow.streaming.sanitization import (
    ProtectedSource,
    identity_for,
    protected_file_source,
    protected_rtsp_source,
)

_BACKENDS = frozenset({"any", "dshow", "ffmpeg", "gstreamer", "msmf", "v4l2"})


def _positive(value: object, *, name: str, allow_zero: bool = False) -> float:
    minimum_ok = float(value) >= 0 if allow_zero and isinstance(value, (int, float)) else False
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not isfinite(value)
        or (not minimum_ok and float(value) <= 0)
    ):
        relation = "non-negative" if allow_zero else "positive"
        raise ConfigurationError(f"{name} must be a finite {relation} number.")
    return float(value)


def _optional_positive(value: object | None, *, name: str) -> float | None:
    if value is None:
        return None
    return _positive(value, name=name)


def _optional_dimension(value: object | None, *, name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigurationError(f"{name} must be a positive integer when provided.")
    return value


def _stream_id(value: str) -> str:
    if not isinstance(value, str) or fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value) is None:
        raise ConfigurationError("Stream ID must be an opaque identifier of at most 64 characters.")
    if any(word in value.lower() for word in ("credential", "password", "secret", "token")):
        raise ConfigurationError("Stream ID must not contain sensitive-field terminology.")
    return value


@dataclass(frozen=True, slots=True)
class ReconnectPolicy:
    """Deterministic bounded exponential backoff for live sources."""

    enabled: bool = True
    initial_delay_seconds: float = 0.25
    maximum_delay_seconds: float = 5.0
    backoff_multiplier: float = 2.0
    maximum_attempts: int | None = 10
    reset_after_stable_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise ConfigurationError("Reconnect enabled must be boolean.")
        initial = _positive(
            self.initial_delay_seconds,
            name="Initial reconnect delay",
            allow_zero=True,
        )
        maximum = _positive(
            self.maximum_delay_seconds,
            name="Maximum reconnect delay",
            allow_zero=True,
        )
        multiplier = _positive(self.backoff_multiplier, name="Reconnect multiplier")
        reset = _positive(
            self.reset_after_stable_seconds,
            name="Reconnect reset duration",
            allow_zero=True,
        )
        if maximum < initial:
            raise ConfigurationError("Maximum reconnect delay must not be below initial delay.")
        if multiplier < 1.0:
            raise ConfigurationError("Reconnect multiplier must be at least 1.")
        if self.maximum_attempts is not None and (
            not isinstance(self.maximum_attempts, int)
            or isinstance(self.maximum_attempts, bool)
            or self.maximum_attempts <= 0
        ):
            raise ConfigurationError("Maximum reconnect attempts must be positive or unlimited.")
        object.__setattr__(self, "initial_delay_seconds", initial)
        object.__setattr__(self, "maximum_delay_seconds", maximum)
        object.__setattr__(self, "backoff_multiplier", multiplier)
        object.__setattr__(self, "reset_after_stable_seconds", reset)

    def delay_for_attempt(self, attempt_number: int) -> float:
        """Return a capped deterministic delay for a one-based attempt."""

        if (
            not isinstance(attempt_number, int)
            or isinstance(attempt_number, bool)
            or attempt_number <= 0
        ):
            raise ConfigurationError("Reconnect attempt number must be positive.")
        return min(
            self.maximum_delay_seconds,
            self.initial_delay_seconds * self.backoff_multiplier ** (attempt_number - 1),
        )

    def permits(self, attempt_number: int) -> bool:
        """Return whether a one-based reconnect attempt is allowed."""

        if not self.enabled:
            return False
        return self.maximum_attempts is None or attempt_number <= self.maximum_attempts


@dataclass(frozen=True, slots=True)
class BufferConfiguration:
    """Fixed-capacity frame-buffer policy."""

    capacity: int = 4
    overflow_policy: OverflowPolicy = OverflowPolicy.DROP_OLDEST

    def __post_init__(self) -> None:
        if (
            not isinstance(self.capacity, int)
            or isinstance(self.capacity, bool)
            or self.capacity <= 0
        ):
            raise ConfigurationError("Buffer capacity must be a positive integer.")
        if not isinstance(self.overflow_policy, OverflowPolicy):
            raise ConfigurationError("Buffer overflow policy is invalid.")


@dataclass(frozen=True, slots=True, repr=False)
class StreamConfiguration:
    """Source configuration with protected runtime locators and safe ``repr``."""

    source_type: SourceType
    stream_id: str
    protected_source: ProtectedSource | None = field(default=None, repr=False)
    device_index: int | None = None
    requested_width: int | None = None
    requested_height: int | None = None
    requested_fps: float | None = None
    backend_preference: str = "any"
    read_timeout_seconds: float | None = 5.0
    warmup_frames: int = 0
    consecutive_failure_limit: int = 3
    temporary_retry_delay_seconds: float = 0.01

    def __post_init__(self) -> None:
        if not isinstance(self.source_type, SourceType):
            raise ConfigurationError("Source type must be explicit.")
        _stream_id(self.stream_id)
        if self.source_type is SourceType.USB:
            if (
                not isinstance(self.device_index, int)
                or isinstance(self.device_index, bool)
                or self.device_index < 0
            ):
                raise ConfigurationError("USB sources require a non-negative device index.")
            if self.protected_source is not None:
                raise ConfigurationError("USB sources must not contain a protected locator.")
        elif self.source_type in {SourceType.RTSP, SourceType.FILE}:
            if not isinstance(self.protected_source, ProtectedSource):
                raise ConfigurationError("RTSP and file sources require a protected locator.")
            if self.protected_source.source_type is not self.source_type:
                raise ConfigurationError("Protected locator type does not match source type.")
            if self.device_index is not None:
                raise ConfigurationError("Only USB sources may contain a device index.")
        elif self.source_type is SourceType.SYNTHETIC:
            if self.protected_source is not None or self.device_index is not None:
                raise ConfigurationError("Synthetic sources do not use external locators.")

        object.__setattr__(
            self,
            "requested_width",
            _optional_dimension(self.requested_width, name="Requested width"),
        )
        object.__setattr__(
            self,
            "requested_height",
            _optional_dimension(self.requested_height, name="Requested height"),
        )
        object.__setattr__(
            self,
            "requested_fps",
            _optional_positive(self.requested_fps, name="Requested FPS"),
        )
        backend = self.backend_preference.strip().lower()
        if backend not in _BACKENDS:
            raise ConfigurationError("Unsupported camera backend preference.")
        object.__setattr__(self, "backend_preference", backend)
        object.__setattr__(
            self,
            "read_timeout_seconds",
            _optional_positive(self.read_timeout_seconds, name="Read timeout"),
        )
        if (
            not isinstance(self.warmup_frames, int)
            or isinstance(self.warmup_frames, bool)
            or self.warmup_frames < 0
        ):
            raise ConfigurationError("Warm-up frame count must be non-negative.")
        if (
            not isinstance(self.consecutive_failure_limit, int)
            or isinstance(self.consecutive_failure_limit, bool)
            or self.consecutive_failure_limit <= 0
        ):
            raise ConfigurationError("Consecutive failure limit must be positive.")
        object.__setattr__(
            self,
            "temporary_retry_delay_seconds",
            _positive(
                self.temporary_retry_delay_seconds,
                name="Temporary retry delay",
                allow_zero=True,
            ),
        )

    @classmethod
    def usb(cls, stream_id: str, device_index: int = 0, **settings: object) -> StreamConfiguration:
        """Create explicit USB camera configuration."""

        return cls(SourceType.USB, stream_id, device_index=device_index, **settings)

    @classmethod
    def rtsp(cls, stream_id: str, url: str, **settings: object) -> StreamConfiguration:
        """Create RTSP configuration without exposing the URL through ``repr``."""

        return cls(
            SourceType.RTSP,
            stream_id,
            protected_source=protected_rtsp_source(url, stream_id),
            **settings,
        )

    @classmethod
    def file(
        cls,
        stream_id: str,
        path: str | Path,
        **settings: object,
    ) -> StreamConfiguration:
        """Create non-live local development-file configuration."""

        return cls(
            SourceType.FILE,
            stream_id,
            protected_source=protected_file_source(path, stream_id),
            **settings,
        )

    @classmethod
    def synthetic(cls, stream_id: str = "synthetic", **settings: object) -> StreamConfiguration:
        """Create deterministic source configuration for tests and CI."""

        return cls(SourceType.SYNTHETIC, stream_id, **settings)

    @property
    def identity(self) -> StreamIdentity:
        """Return the sanitized identity shared by health and frame packets."""

        return identity_for(self.source_type, self.stream_id)

    def __repr__(self) -> str:
        return (
            "StreamConfiguration("
            f"source_type={self.source_type.value!r}, stream_id={self.stream_id!r}, "
            f"source={self.identity.display_name!r}, requested_width={self.requested_width!r}, "
            f"requested_height={self.requested_height!r}, requested_fps={self.requested_fps!r}, "
            f"backend_preference={self.backend_preference!r})"
        )


__all__ = ["BufferConfiguration", "ReconnectPolicy", "StreamConfiguration"]
