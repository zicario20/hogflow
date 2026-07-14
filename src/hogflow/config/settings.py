"""Minimal immutable settings used by the HogFlow architecture foundation."""

from __future__ import annotations

from dataclasses import dataclass, field

from hogflow.core import ConfigurationError

_SUPPORTED_LOGGING_LEVELS = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


@dataclass(frozen=True, slots=True)
class LoggingSettings:
    """Validated logging settings for a HogFlow runtime."""

    level: str = "INFO"

    def __post_init__(self) -> None:
        if not isinstance(self.level, str):
            raise ConfigurationError("Logging level must be a string.")
        normalized_level = self.level.strip().upper()
        if normalized_level not in _SUPPORTED_LOGGING_LEVELS:
            raise ConfigurationError(f"Unsupported logging level: {self.level!r}.")
        object.__setattr__(self, "level", normalized_level)


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Foundational immutable settings for one HogFlow runtime."""

    logging: LoggingSettings = field(default_factory=LoggingSettings)

    def __post_init__(self) -> None:
        if not isinstance(self.logging, LoggingSettings):
            raise ConfigurationError("RuntimeSettings.logging must be LoggingSettings.")
