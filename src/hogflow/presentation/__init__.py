"""Snapshot-driven Phase 9 operator presentation and local diagnostics."""

from hogflow.presentation.desktop import (
    TkOperatorView,
    create_tk_operator_view,
    parse_register_truck_form,
    parse_session_plan,
    parse_video_source_form,
    run_operator_desktop,
)
from hogflow.presentation.models import (
    CameraPipelinePanel,
    ConfirmationKind,
    ConfirmationRequest,
    CountingLanePanel,
    DockPanel,
    OperatorAction,
    OperatorActionState,
    OperatorScreen,
    OperatorStatus,
    TotalsPanel,
)
from hogflow.presentation.ports import OperatorDesktopView, OperatorPreviewView, OperatorView
from hogflow.presentation.presenter import OperatorPresenter, screen_from_snapshot
from hogflow.presentation.preview import (
    PreviewPrimitive,
    PreviewPrimitiveKind,
    PreviewRenderPlan,
    build_preview_render_plan,
)

__all__ = [
    "ConfirmationKind",
    "ConfirmationRequest",
    "CameraPipelinePanel",
    "CountingLanePanel",
    "DockPanel",
    "OperatorAction",
    "OperatorActionState",
    "OperatorDesktopView",
    "OperatorPresenter",
    "OperatorPreviewView",
    "OperatorScreen",
    "OperatorStatus",
    "OperatorView",
    "PreviewPrimitive",
    "PreviewPrimitiveKind",
    "PreviewRenderPlan",
    "TkOperatorView",
    "TotalsPanel",
    "create_tk_operator_view",
    "build_preview_render_plan",
    "parse_register_truck_form",
    "parse_session_plan",
    "parse_video_source_form",
    "run_operator_desktop",
    "screen_from_snapshot",
]
