"""Presentation view contract for a testable operator workflow."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hogflow.presentation.models import OperatorScreen


@runtime_checkable
class OperatorView(Protocol):
    """Small output boundary implemented by desktop and test views."""

    def render(self, screen: OperatorScreen) -> None:
        """Render one fresh immutable screen model."""

    def show_error(self, message: str) -> None:
        """Display one expected domain/application error."""


__all__ = ["OperatorView"]
