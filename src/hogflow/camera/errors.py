"""Sanitized application errors for the shared camera-counting runtime."""

from hogflow.core import HogFlowError


class CameraPipelineError(HogFlowError):
    """Base error for the Phase 9.3 camera orchestration boundary."""


class CameraPipelineConfigurationError(CameraPipelineError):
    """Raised when a source or processor configuration is invalid."""


class CameraPipelineLifecycleError(CameraPipelineError):
    """Raised when a pipeline command violates its explicit lifecycle."""


class CameraPipelineProcessingError(CameraPipelineError):
    """Raised when detector, tracker, or crossing processing cannot continue."""


class CameraPipelineShutdownError(CameraPipelineError):
    """Raised when the single worker or source cannot close deterministically."""


class StaleCameraEvidenceError(CameraPipelineError):
    """Raised when delayed crossing evidence no longer owns the shared lane."""


__all__ = [
    "CameraPipelineConfigurationError",
    "CameraPipelineError",
    "CameraPipelineLifecycleError",
    "CameraPipelineProcessingError",
    "CameraPipelineShutdownError",
    "StaleCameraEvidenceError",
]
