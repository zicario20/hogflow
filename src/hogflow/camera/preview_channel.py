"""Thread-safe latest-frame-only channel for optional operator preview."""

from __future__ import annotations

from threading import Lock
from time import monotonic
from typing import Callable

from hogflow.camera.preview_models import (
    PreviewConfiguration,
    PreviewFailureCategory,
    PreviewFrame,
    PreviewHealthState,
    PreviewSnapshot,
)


class LatestPreviewFrameChannel:
    """Retain at most one immutable visual frame.

    ``publish`` never waits for UI consumption. A new frame atomically replaces
    the old slot, and ``take_latest`` marks that slot as delivered without
    deleting its pixels. ``retained_latest`` may therefore freeze the final
    frame after local-file EOF while the channel still owns exactly one frame.
    No list, queue, playback buffer, or frame history exists.
    """

    def __init__(
        self,
        configuration: PreviewConfiguration = PreviewConfiguration(),
        *,
        monotonic_clock: Callable[[], float] = monotonic,
    ) -> None:
        if not isinstance(configuration, PreviewConfiguration):
            raise TypeError("Preview channel requires PreviewConfiguration.")
        if not callable(monotonic_clock):
            raise TypeError("Preview channel monotonic clock must be callable.")
        self._configuration = configuration
        self._clock = monotonic_clock
        self._lock = Lock()
        self._latest: PreviewFrame | None = None
        self._frame_available = False
        self._closed = False
        self._rendering_failed = False
        self._frames_published = 0
        self._frames_replaced = 0
        self._frames_consumed = 0
        self._publication_failures = 0
        self._render_failures = 0
        self._first_publish_at: float | None = None
        self._last_publish_at: float | None = None
        self._last_frame_sequence: int | None = None
        self._failure_category = PreviewFailureCategory.NONE
        self._failure_message: str | None = None

    @property
    def enabled(self) -> bool:
        return self._configuration.enabled

    def publish(self, frame: PreviewFrame) -> None:
        """Replace the current visual slot without waiting for the UI."""

        if not isinstance(frame, PreviewFrame):
            raise TypeError("Preview publication requires an immutable PreviewFrame.")
        if not self.enabled:
            return
        now = float(self._clock())
        with self._lock:
            if self._closed or self._rendering_failed:
                return
            if self._frame_available:
                self._frames_replaced += 1
            self._latest = frame
            self._frame_available = True
            self._frames_published += 1
            self._first_publish_at = (
                now if self._first_publish_at is None else self._first_publish_at
            )
            self._last_publish_at = now
            self._last_frame_sequence = frame.frame_sequence
            if self._failure_category is PreviewFailureCategory.PUBLICATION:
                self._failure_category = PreviewFailureCategory.NONE
                self._failure_message = None

    def take_latest(self) -> PreviewFrame | None:
        """Return the newest undelivered frame, if one is available."""

        with self._lock:
            if not self.enabled or self._closed or self._rendering_failed:
                return None
            frame = self._latest if self._frame_available else None
            if frame is not None:
                self._frame_available = False
                self._frames_consumed += 1
            return frame

    def retained_latest(self) -> PreviewFrame | None:
        """Return the one retained frame without changing delivery telemetry."""

        with self._lock:
            if not self.enabled or self._closed or self._rendering_failed:
                return None
            return self._latest

    def record_publication_failure(self) -> None:
        """Record one isolated overlay/publication failure and keep counting live."""

        if not self.enabled:
            return
        with self._lock:
            if self._closed:
                return
            self._publication_failures += 1
            self._failure_category = PreviewFailureCategory.PUBLICATION
            self._failure_message = "Live preview frame could not be prepared; counting continues."

    def record_render_failure(self) -> PreviewSnapshot:
        """Disable rendering after one UI failure without affecting the worker."""

        if not self.enabled:
            return self.snapshot()
        with self._lock:
            if not self._closed and not self._rendering_failed:
                self._render_failures += 1
                self._rendering_failed = True
                self._latest = None
                self._frame_available = False
                self._failure_category = PreviewFailureCategory.RENDERING
                self._failure_message = "Live preview rendering stopped; counting continues."
            return self._snapshot_locked()

    def reset(self) -> None:
        """Clear ephemeral state for one new pipeline run."""

        with self._lock:
            if self._closed:
                return
            self._latest = None
            self._frame_available = False
            self._rendering_failed = False
            self._frames_published = 0
            self._frames_replaced = 0
            self._frames_consumed = 0
            self._publication_failures = 0
            self._render_failures = 0
            self._first_publish_at = None
            self._last_publish_at = None
            self._last_frame_sequence = None
            self._failure_category = PreviewFailureCategory.NONE
            self._failure_message = None

    def clear(self) -> None:
        """Drop the current frame while retaining bounded run telemetry."""

        with self._lock:
            self._latest = None
            self._frame_available = False

    def close(self) -> None:
        """Permanently close the visual channel; repeated calls are safe."""

        with self._lock:
            self._latest = None
            self._frame_available = False
            self._closed = True

    def snapshot(self) -> PreviewSnapshot:
        """Return bounded telemetry without exposing pixels."""

        with self._lock:
            return self._snapshot_locked()

    def _snapshot_locked(self) -> PreviewSnapshot:
        if not self.enabled:
            health = PreviewHealthState.DISABLED
        elif self._closed:
            health = PreviewHealthState.CLOSED
        elif self._rendering_failed:
            health = PreviewHealthState.FAILED
        elif self._failure_category is PreviewFailureCategory.PUBLICATION:
            health = PreviewHealthState.DEGRADED
        elif self._frame_available:
            health = PreviewHealthState.AVAILABLE
        else:
            health = PreviewHealthState.WAITING
        return PreviewSnapshot(
            enabled=self.enabled,
            health_state=health,
            frame_available=self._frame_available,
            frames_published=self._frames_published,
            frames_replaced=self._frames_replaced,
            frames_consumed=self._frames_consumed,
            publication_failures=self._publication_failures,
            render_failures=self._render_failures,
            effective_preview_fps=self._effective_fps(),
            last_frame_sequence=self._last_frame_sequence,
            failure_category=self._failure_category,
            failure_message=self._failure_message,
        )

    def _effective_fps(self) -> float:
        if (
            self._frames_published < 2
            or self._first_publish_at is None
            or self._last_publish_at is None
        ):
            return 0.0
        duration = self._last_publish_at - self._first_publish_at
        return 0.0 if duration <= 0 else (self._frames_published - 1) / duration


__all__ = ["LatestPreviewFrameChannel"]
