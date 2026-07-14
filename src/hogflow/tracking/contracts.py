"""Framework-independent multi-object tracking contract."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from hogflow.models import Detection, Frame, Track


class Tracker(Protocol):
    """Describe reusable frame-to-frame identity association without an algorithm.

    A tracker receives one immutable :class:`~hogflow.models.Frame` and the
    immutable detections belonging to that frame, then returns an immutable
    sequence of immutable :class:`~hogflow.models.Track` objects. Implementations
    own their association state and resources. Callers own returned values and
    may retain them, but tracker IDs remain valid only for the lifetime defined
    by the implementation; they are not biological, business, database, count,
    or session identifiers.

    The protocol does not detect, count, render, schedule work, manage sessions,
    expose configuration, or guarantee persistence, latency, or thread safety.
    Implementations must convert framework objects at their boundary. Expected
    input, dependency, and runtime failures should use documented HogFlow
    exceptions where appropriate, while programming errors must remain visible.
    The protocol introduces no randomness; repeatability for identical ordered
    frames, detections, initialization, and configuration is an implementation
    responsibility.
    """

    def update(self, frame: Frame, detections: Sequence[Detection]) -> Sequence[Track]:
        """Associate one frame's detections and return implementation-scoped tracks.

        The returned sequence is caller-owned and must not be mutated by the
        implementation after return. No framework-specific object may cross
        this boundary.
        """

        ...


__all__ = ["Tracker"]
