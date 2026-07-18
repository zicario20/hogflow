"""Expected, sanitized failures for live camera acquisition."""

from hogflow.core import HogFlowError


class StreamingError(HogFlowError):
    """Base exception for expected stream-acquisition failures."""


class StreamOpenError(StreamingError):
    """Raised when a configured source cannot be opened safely."""


class StreamFatalReadError(StreamingError):
    """Raised when a source cannot continue after a read failure."""


class StreamLifecycleError(StreamingError):
    """Raised for invalid runner or source lifecycle operations."""


class BufferClosedError(StreamingError):
    """Raised when a producer submits after buffer shutdown."""


__all__ = [
    "BufferClosedError",
    "StreamFatalReadError",
    "StreamLifecycleError",
    "StreamOpenError",
    "StreamingError",
]
