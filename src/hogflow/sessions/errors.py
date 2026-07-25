"""Expected failures at the unloading-session/counting application boundary."""

from hogflow.core import HogFlowError


class SessionCountingIntegrationError(HogFlowError):
    """Base class for expected Phase 8.2 integration failures."""


class SessionCountingConfigurationError(SessionCountingIntegrationError):
    """Raised when the service cannot be configured safely."""


class SessionCountingLifecycleError(SessionCountingIntegrationError):
    """Raised when a command conflicts with the active session lifecycle."""


class SessionCountingLifecycleReuseError(SessionCountingLifecycleError):
    """Raised when a prior crossing or counting lifecycle would be reused."""


class SessionCountingTransferError(SessionCountingIntegrationError):
    """Raised when a lifecycle total cannot be transferred atomically."""


__all__ = [
    "SessionCountingConfigurationError",
    "SessionCountingIntegrationError",
    "SessionCountingLifecycleError",
    "SessionCountingLifecycleReuseError",
    "SessionCountingTransferError",
]
