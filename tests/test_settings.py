from dataclasses import FrozenInstanceError

import pytest

from hogflow.config import LoggingSettings, RuntimeSettings
from hogflow.core import ConfigurationError


@pytest.mark.parametrize("level", ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"])
def test_logging_settings_accepts_supported_level(level: str) -> None:
    settings = LoggingSettings(level=level)

    assert settings.level == level


def test_logging_settings_normalizes_level_to_uppercase() -> None:
    settings = LoggingSettings(level=" debug ")

    assert settings.level == "DEBUG"


@pytest.mark.parametrize("level", ["", "TRACE", "verbose"])
def test_logging_settings_rejects_invalid_level(level: str) -> None:
    with pytest.raises(ConfigurationError):
        LoggingSettings(level=level)


def test_logging_settings_is_immutable() -> None:
    settings = LoggingSettings()

    with pytest.raises(FrozenInstanceError):
        settings.level = "DEBUG"  # type: ignore[misc]


def test_runtime_settings_uses_default_logging_settings() -> None:
    settings = RuntimeSettings()

    assert settings.logging == LoggingSettings(level="INFO")


def test_runtime_settings_rejects_invalid_logging_object() -> None:
    with pytest.raises(ConfigurationError):
        RuntimeSettings(logging=object())  # type: ignore[arg-type]
