"""Small framework-neutral behavior contract for live crossing detection."""

from __future__ import annotations

from typing import Protocol

from hogflow.counting.live_models import (
    LiveCrossingConfiguration,
    LiveCrossingResult,
    LiveCrossingStats,
)
from hogflow.tracking.models import TrackingResult


class LiveCrossingDetector(Protocol):
    """Emit geometric events for one stream and tracker lifecycle.

    Implementations retain only bounded temporary side state. They perform no
    detection, tracking, accumulated counting, deduplication, session work,
    persistence, rendering, or permanent identity assignment.
    """

    @property
    def configuration(self) -> LiveCrossingConfiguration:
        """Return immutable crossing configuration."""

        ...

    @property
    def is_started(self) -> bool:
        """Return whether crossing state is bound to a stream lifecycle."""

        ...

    def start(self, source_id: str) -> None:
        """Bind crossing state to one opaque source lifecycle."""

        ...

    def update(self, tracking: TrackingResult) -> LiveCrossingResult:
        """Process one newer tracking result and emit zero or more events."""

        ...

    def reset(self) -> None:
        """Clear all side state and begin a new tracker lifecycle identity."""

        ...

    def close(self) -> None:
        """Clear state; repeated calls must be safe."""

        ...

    def statistics(self) -> LiveCrossingStats:
        """Return bounded aggregate diagnostics."""

        ...

    def record_preview_failure(self) -> None:
        """Record one isolated local-preview failure."""

        ...


__all__ = ["LiveCrossingDetector"]
