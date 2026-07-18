"""Shared errors and logging foundations for HogFlow.

Current status: FOUNDATION ONLY — introduced in Phase 2.1.
"""

from hogflow.core.errors import (
    ConfigurationError,
    DependencyUnavailableError,
    HogFlowError,
    InputDataError,
)
from hogflow.core.identifiers import phase4_clip_id
from hogflow.core.logging_config import configure_logging, get_logger

__all__ = [
    "ConfigurationError",
    "DependencyUnavailableError",
    "HogFlowError",
    "InputDataError",
    "configure_logging",
    "get_logger",
    "phase4_clip_id",
]
