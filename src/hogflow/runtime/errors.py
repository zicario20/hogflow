"""Sanitized errors for the Phase 10.1 production runtime boundary."""

from hogflow.core import HogFlowError


class ProductionRuntimeError(HogFlowError):
    """Base expected error for production-runtime supervision."""


class ProductionRuntimeConfigurationError(ProductionRuntimeError):
    """Raised when runtime safety thresholds are invalid."""


class ProductionRuntimeLifecycleError(ProductionRuntimeError):
    """Raised when a runtime command violates supervisor lifecycle."""


class UnsafeRuntimeRestartError(ProductionRuntimeLifecycleError):
    """Raised when restart would reset identities during active counting."""


class RuntimeRestartLimitError(ProductionRuntimeLifecycleError):
    """Raised when a bounded manual restart budget is exhausted."""


__all__ = [
    "ProductionRuntimeConfigurationError",
    "ProductionRuntimeError",
    "ProductionRuntimeLifecycleError",
    "RuntimeRestartLimitError",
    "UnsafeRuntimeRestartError",
]
