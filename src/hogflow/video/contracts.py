"""Framework-independent video-source contract."""

from __future__ import annotations

from typing import Protocol

from hogflow.models import Frame


class VideoSource(Protocol):
    """Describe sequential access to immutable video frames.

    A video source owns its input resource and any mutable decoding state. Each
    call to :meth:`read` transfers an immutable :class:`~hogflow.models.Frame`
    to the caller, which may retain it. ``None`` denotes normal end of input.
    The caller owns the source lifetime and must call :meth:`close` when reading
    is complete.

    The protocol does not select a decoder, open a camera by itself, schedule
    work, detect, track, count, buffer, or guarantee seeking, latency, or thread
    safety. Implementations must keep framework-specific frame objects private.
    Expected input, dependency, decoding, and resource failures should use
    documented HogFlow exceptions where appropriate; programming errors must
    remain visible. Given an identical source and configuration, sequence
    repeatability remains an implementation responsibility.
    """

    def read(self) -> Frame | None:
        """Return the next immutable frame, or ``None`` at normal end of input."""

        ...

    def close(self) -> None:
        """Release resources owned by this source implementation."""

        ...


__all__ = ["VideoSource"]
