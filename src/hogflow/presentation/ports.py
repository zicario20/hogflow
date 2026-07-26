"""Presentation view contract for a testable operator workflow."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from hogflow.presentation.models import CameraPipelinePanel, ConfirmationRequest, OperatorScreen
from hogflow.presentation.preview import PreviewRenderPlan


@runtime_checkable
class OperatorView(Protocol):
    """Small output boundary implemented by desktop and test views."""

    def render(self, screen: OperatorScreen) -> None:
        """Render one fresh immutable screen model."""

    def show_error(self, message: str) -> None:
        """Display one expected domain/application error."""

    def confirm(self, request: ConfirmationRequest) -> bool:
        """Ask the operator to confirm one destructive action."""

    def close(self) -> None:
        """Close the local presentation after application shutdown."""


@runtime_checkable
class OperatorDesktopView(OperatorView, Protocol):
    """One-window desktop lifecycle used only by the composition root."""

    def bind_presenter(self, presenter: object) -> None:
        """Attach the presenter once after both sides are constructed."""

    def start(self) -> None:
        """Render once and run the local toolkit loop."""


@runtime_checkable
class OperatorPreviewView(Protocol):
    """Optional visual surface implemented by the Phase 9.4 desktop."""

    def render_preview(
        self,
        plan: PreviewRenderPlan | None,
        diagnostics: CameraPipelinePanel,
    ) -> None:
        """Render one latest visual plan or an explicit unavailable state."""


__all__ = ["OperatorDesktopView", "OperatorPreviewView", "OperatorView"]
