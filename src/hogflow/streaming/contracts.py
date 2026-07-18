"""Framework-neutral contract for camera and development stream sources."""

from __future__ import annotations

from typing import Protocol

from hogflow.streaming.models import (
    StreamHealth,
    StreamIdentity,
    StreamReadResult,
    StreamStatistics,
)


class CameraSource(Protocol):
    """Provide synchronous sequential acquisition behind a replaceable boundary.

    A source owns its device, connection, decoder, and mutable acquisition
    state. ``open`` and ``close`` define explicit lifecycle ownership. ``read``
    returns an explicit frame, temporary-unavailable, EOF, interruption, or
    stopped result; fatal failures raise documented stream exceptions.

    Returned payload bytes are immutable and caller-owned. The protocol does
    not detect, track, count, buffer, reconnect, persist frames, promise camera
    settings, guarantee thread safety, or expose a framework object. Consumers
    must assume blocking synchronous reads and use orchestration when they need
    another thread or future asynchronous integration.
    """

    @property
    def identity(self) -> StreamIdentity:
        """Return a sanitized source identity safe for output."""

        ...

    @property
    def is_live(self) -> bool:
        """Return whether loss of frames represents a reconnectable live source."""

        ...

    def open(self) -> None:
        """Acquire source resources or raise a sanitized open failure."""

        ...

    def read(self) -> StreamReadResult:
        """Read one explicit result from the currently open source."""

        ...

    def close(self) -> None:
        """Release source resources; repeated calls must be safe."""

        ...

    def is_open(self) -> bool:
        """Return whether the source currently owns an open resource."""

        ...

    def health(self) -> StreamHealth:
        """Return a bounded sanitized health snapshot."""

        ...

    def statistics(self) -> StreamStatistics:
        """Return immutable aggregate source statistics."""

        ...


__all__ = ["CameraSource"]
