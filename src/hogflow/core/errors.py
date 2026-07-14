"""Project-specific exceptions for expected HogFlow application failures."""


class HogFlowError(Exception):
    """Base exception for expected HogFlow application errors."""


class ConfigurationError(HogFlowError):
    """Raised when explicit HogFlow configuration is invalid."""


class DependencyUnavailableError(HogFlowError):
    """Raised when an optional runtime dependency is unavailable."""


class InputDataError(HogFlowError):
    """Raised when user-provided input data is missing or invalid."""
