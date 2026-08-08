from __future__ import annotations

from dataclasses import replace

from _phase9_helpers import operator_application
from test_operator_desktop_scrolling import _is_descendant, _view, _walk_widgets

from hogflow.presentation import screen_from_snapshot
from hogflow.presentation.models import OperatorAction
from hogflow.presentation.theme import (
    HMI_THEME,
    OperatorMode,
    SemanticTone,
    operator_mode_for_source_type,
    semantic_tone_for_status,
)


def _label_texts(view) -> set[str]:
    return {
        str(widget.options["text"])
        for widget in _walk_widgets(view._scroll_content)
        if "text" in widget.options
    }


def test_operator_modes_are_evidence_based_and_never_claim_production() -> None:
    assert operator_mode_for_source_type(None) is OperatorMode.VALIDATION_BUILD
    assert operator_mode_for_source_type("synthetic") is OperatorMode.VALIDATION_BUILD
    assert operator_mode_for_source_type("file") is OperatorMode.VALIDATION_MODE
    assert operator_mode_for_source_type("usb") is OperatorMode.LIVE_MODE
    assert operator_mode_for_source_type("rtsp") is OperatorMode.LIVE_MODE
    assert all("PRODUCTION" not in mode.value for mode in OperatorMode)


def test_hmi_theme_has_semantic_statuses_and_readable_visual_priority() -> None:
    assert semantic_tone_for_status("Running") is SemanticTone.SUCCESS
    assert semantic_tone_for_status("Reconnecting") is SemanticTone.WARNING
    assert semantic_tone_for_status("Failed") is SemanticTone.CRITICAL
    assert semantic_tone_for_status("Stopped") is SemanticTone.INACTIVE
    assert semantic_tone_for_status("Occupied") is SemanticTone.INFORMATION
    assert HMI_THEME.typography.live_count_size > HMI_THEME.typography.metric_size
    assert HMI_THEME.typography.metric_size >= HMI_THEME.typography.body_size
    assert HMI_THEME.colors.background != HMI_THEME.colors.panel
    assert HMI_THEME.colors.text_primary != HMI_THEME.colors.text_muted


def test_hmi_layout_has_compact_brand_header_and_operational_hierarchy() -> None:
    view, root = _view()
    labels = _label_texts(view)

    assert root.title_value == "HogFlow — AI Livestock Receiving & Counting"
    assert view._header_panel.grid_options["row"] == 0
    assert _is_descendant(view._header_panel, view._scroll_content)
    assert "HogFlow" in labels
    assert "AI Livestock Receiving & Counting" in labels
    assert view._mode_value.get() == "VALIDATION BUILD"
    assert "SOURCE → DETECTOR → TRACKER → CROSSING → COUNTER → SHARED LANE" in labels
    assert view._lane_count_widget.options["font"][1] == HMI_THEME.typography.live_count_size
    assert (
        view._pipeline_metric_widgets["fps"].options["font"][1]
        < (view._lane_count_widget.options["font"][1])
    )
    assert _is_descendant(view._actions_panel, view._scroll_content)
    assert _is_descendant(view._preview_panel, view._scroll_content)


def test_render_updates_mode_and_semantic_visual_state_from_snapshot() -> None:
    application, _coordinator = operator_application()
    base = screen_from_snapshot(application.snapshot())
    view, _root = _view()

    view.render(base)
    assert view._mode_value.get() == "VALIDATION BUILD"

    file_screen = replace(
        base,
        camera_pipeline=replace(
            base.camera_pipeline,
            source="file-camera:shared_operator_lane",
            source_type="file",
            camera_status="Exhausted",
            pipeline_status="Stopped",
            preview_status="End of Video",
        ),
    )
    view.render(file_screen)
    assert view._mode_value.get() == "VALIDATION MODE"
    assert view._camera_state_value.get() == "CAMERA EXHAUSTED"
    assert view._mode_badge.options["foreground"] == HMI_THEME.colors.information

    live_screen = replace(
        base,
        camera_pipeline=replace(
            base.camera_pipeline,
            source="usb-camera:shared_operator_lane",
            source_type="usb",
            camera_status="Running",
            pipeline_status="Running",
        ),
    )
    view.render(live_screen)
    assert view._mode_value.get() == "LIVE MODE"
    assert view._camera_state_value.get() == "CAMERA RUNNING"
    assert view._pipeline_state_value.get() == "PIPELINE RUNNING"
    assert view._camera_state_widget.options["foreground"] == HMI_THEME.colors.success


def test_dock_cards_keep_approved_wide_order_and_theme_semantics() -> None:
    view, _root = _view()

    assert view._dock_panels[next(iter(view._dock_panels))].options["background"] == (
        HMI_THEME.colors.panel
    )
    positions = {
        dock.sequence_number: (
            view._dock_panels[dock].grid_options["row"],
            view._dock_panels[dock].grid_options["column"],
        )
        for dock in view._dock_panels
    }
    assert positions == {1: (0, 0), 2: (1, 0), 3: (0, 1), 4: (1, 1)}


def test_disabled_actions_use_neutral_treatment_without_changing_eligibility() -> None:
    application, _coordinator = operator_application()
    screen = screen_from_snapshot(application.snapshot())
    view, _root = _view()

    view.render(screen)

    disabled = view._buttons[OperatorAction.START_PIPELINE]
    enabled = view._buttons[OperatorAction.CONFIGURE_SOURCE]
    assert disabled.options["state"] == "disabled"
    assert disabled.options["background"] == HMI_THEME.colors.surface
    assert enabled.options["state"] == "normal"
    assert (
        enabled.options["background"]
        == view._button_style_options[OperatorAction.CONFIGURE_SOURCE]["background"]
    )
