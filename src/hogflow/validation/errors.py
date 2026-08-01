"""Expected failures for controlled Phase 10.3 local validation."""

from hogflow.core import ConfigurationError, HogFlowError, InputDataError


class RealWorldValidationError(HogFlowError):
    """Base class for expected controlled real-video validation failures."""


class ValidationConfigurationError(ConfigurationError, RealWorldValidationError):
    """Raised when an offline validation configuration is invalid."""


class AuthorizedVideoError(InputDataError, RealWorldValidationError):
    """Raised when an authorized-video requirement is violated."""


class ModelAvailabilityError(InputDataError, RealWorldValidationError):
    """Raised when a local model violates the explicit artifact gate."""


class ValidationExecutionError(RealWorldValidationError):
    """Raised when a model-present validation run cannot execute safely."""


class ValidationOutputError(RealWorldValidationError):
    """Raised when a sanitized local report cannot be written."""


__all__ = [
    "AuthorizedVideoError",
    "ModelAvailabilityError",
    "RealWorldValidationError",
    "ValidationConfigurationError",
    "ValidationExecutionError",
    "ValidationOutputError",
]
