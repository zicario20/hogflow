"""Framework-independent object-detection contract."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from hogflow.models import Detection, Frame


class Detector(Protocol):
    """Describe one reusable object detector without prescribing its implementation.

    A detector receives one immutable :class:`~hogflow.models.Frame` and returns
    an immutable sequence of immutable :class:`~hogflow.models.Detection`
    objects. The implementation owns model loading, configuration, resources,
    and any internal state; callers own the returned values and may retain
    them. The protocol does not detect across batches, track identities, count,
    render, write files, manage sessions, or guarantee latency or thread safety.

    Implementations must convert framework results before returning. Expected
    input, dependency, and inference failures should use documented HogFlow
    exceptions where appropriate, while programming errors must remain visible.
    No construction behavior or implementation lifetime is prescribed. The
    protocol introduces no randomness; repeatability for an identical frame,
    model, and configuration remains an implementation responsibility.
    """

    def predict(self, frame: Frame) -> Sequence[Detection]:
        """Return zero or more immutable detections for exactly one frame.

        The returned sequence is caller-owned and must not be mutated by the
        implementation after return. No framework-specific object may escape
        through either the input or output boundary.
        """

        ...


__all__ = ["Detector"]
