"""Expected failures for offline virtual-line position evaluation."""

from hogflow.core import ConfigurationError, HogFlowError, InputDataError


class LineEvaluationError(HogFlowError):
    """Base class for expected Phase 6 evaluation failures."""


class LineEvaluationConfigurationError(ConfigurationError, LineEvaluationError):
    """Raised when a candidate, plan, or ranking configuration is invalid."""


class TrackingReplayError(InputDataError, LineEvaluationError):
    """Raised when an offline tracking replay is structurally invalid."""


class LineEvaluationSchemaError(InputDataError, LineEvaluationError):
    """Raised when a Phase 6 JSON document violates its versioned schema."""


class GroundTruthMatchingError(InputDataError, LineEvaluationError):
    """Raised when crossing-event matching input or configuration is invalid."""


class LineEvaluationExecutionError(LineEvaluationError):
    """Raised when one candidate cannot be evaluated safely."""


class LineEvaluationOutputError(LineEvaluationError):
    """Raised when a sanitized evaluation document cannot be written."""


__all__ = [
    "GroundTruthMatchingError",
    "LineEvaluationConfigurationError",
    "LineEvaluationError",
    "LineEvaluationExecutionError",
    "LineEvaluationOutputError",
    "LineEvaluationSchemaError",
    "TrackingReplayError",
]
