"""Central logging configuration for HogFlow application entrypoints."""

from __future__ import annotations

import logging

from hogflow.core.errors import ConfigurationError

_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_STANDARD_LEVEL_NAMES = frozenset({"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"})


def configure_logging(
    level: int | str = logging.INFO,
    *,
    force: bool = False,
) -> None:
    """Configure concise console logging for a HogFlow application entrypoint.

    Calling this function repeatedly with ``force=False`` relies on
    :func:`logging.basicConfig` to preserve the existing root handlers rather
    than adding duplicates.
    """

    validated_level: int | str
    if isinstance(level, str):
        validated_level = level.strip().upper()
        if validated_level not in _STANDARD_LEVEL_NAMES:
            raise ConfigurationError(f"Unsupported logging level: {level!r}.")
    elif isinstance(level, int) and not isinstance(level, bool):
        validated_level = level
    else:
        raise ConfigurationError("Logging level must be an integer or standard level name.")

    logging.basicConfig(
        level=validated_level,
        format=_LOG_FORMAT,
        datefmt=_DATE_FORMAT,
        force=force,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger without configuring global logging."""

    if not isinstance(name, str) or not name.strip():
        raise ConfigurationError("Logger name must be a non-empty string.")
    return logging.getLogger(name)
