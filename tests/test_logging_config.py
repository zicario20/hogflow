import logging
from unittest.mock import patch

import pytest

from hogflow.core import ConfigurationError, configure_logging, get_logger


def test_get_logger_returns_named_logger_without_configuring_logging() -> None:
    root_logger = logging.getLogger()
    original_handlers = tuple(root_logger.handlers)

    logger = get_logger("hogflow.test")

    assert logger is logging.getLogger("hogflow.test")
    assert tuple(root_logger.handlers) == original_handlers


@pytest.mark.parametrize("name", ["", "   "])
def test_get_logger_rejects_empty_name(name: str) -> None:
    with pytest.raises(ConfigurationError):
        get_logger(name)


@pytest.mark.parametrize("level", ["TRACE", "", object()])
def test_configure_logging_rejects_invalid_level(level: object) -> None:
    with pytest.raises(ConfigurationError):
        configure_logging(level)  # type: ignore[arg-type]


def test_configure_logging_accepts_integer_level_and_force() -> None:
    with patch("hogflow.core.logging_config.logging.basicConfig") as basic_config:
        configure_logging(logging.ERROR, force=True)

    basic_config.assert_called_once_with(
        level=logging.ERROR,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )


def test_configure_logging_does_not_duplicate_handlers() -> None:
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    original_level = root_logger.level

    try:
        root_logger.handlers.clear()
        configure_logging("debug")
        configured_handlers = tuple(root_logger.handlers)

        configure_logging("INFO")

        assert configured_handlers
        assert tuple(root_logger.handlers) == configured_handlers
        assert root_logger.level == logging.DEBUG
    finally:
        for handler in root_logger.handlers:
            if handler not in original_handlers:
                handler.close()
        root_logger.handlers[:] = original_handlers
        root_logger.setLevel(original_level)
