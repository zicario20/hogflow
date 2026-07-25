"""Small framework-neutral behavior contract for live directional counting."""

from __future__ import annotations

from typing import Protocol

from hogflow.counting.live_counting_models import (
    LiveCountingConfiguration,
    LiveCountingResult,
    LiveCountingStats,
)
from hogflow.counting.live_models import LiveCrossingResult


class LiveDirectionalCounter(Protocol):
    """Apply one explicit counting policy within one crossing lifecycle."""

    @property
    def configuration(self) -> LiveCountingConfiguration:
        """Return immutable counting configuration."""

        ...

    @property
    def is_started(self) -> bool:
        """Return whether the counter is bound to one active lifecycle."""

        ...

    @property
    def source_id(self) -> str:
        """Return the opaque active source ID."""

        ...

    @property
    def crossing_lifecycle_id(self) -> str:
        """Return the active Phase 5.4 crossing lifecycle ID."""

        ...

    @property
    def counting_lifecycle_id(self) -> str:
        """Return the distinct active counting lifecycle ID."""

        ...

    def start(self, source_id: str, crossing_lifecycle_id: str) -> None:
        """Start fresh state for one source and crossing lifecycle."""

        ...

    def update(self, crossing: LiveCrossingResult) -> LiveCountingResult:
        """Atomically process one newer crossing result."""

        ...

    def reset(self, crossing_lifecycle_id: str) -> None:
        """Clear total and identities for a new crossing lifecycle."""

        ...

    def close(self) -> None:
        """Clear active state; repeated calls must be safe."""

        ...

    def statistics(self) -> LiveCountingStats:
        """Return bounded aggregate diagnostics."""

        ...

    def record_preview_failure(self) -> None:
        """Record one isolated local-preview failure."""

        ...


__all__ = ["LiveDirectionalCounter"]
