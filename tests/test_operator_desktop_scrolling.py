from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from hogflow.application import DockId
from hogflow.presentation import OperatorAction, TkOperatorView


class FakeVariable:
    def __init__(self, value: str = "") -> None:
        self.value = value

    def get(self) -> str:
        return self.value

    def set(self, value: str) -> None:
        self.value = value


class FakeWidget:
    widget_class = "Frame"

    def __init__(self, parent: Any = None, *args: Any, **options: Any) -> None:
        del args
        self.parent = parent
        self.options = dict(options)
        self.children: list[FakeWidget] = []
        self.grid_options: dict[str, Any] = {}
        self.bindings: dict[str, list[tuple[str, Any]]] = {}
        self.column_weights: dict[int, int] = {}
        self.row_weights: dict[int, int] = {}
        if isinstance(parent, FakeWidget):
            parent.children.append(self)

    def grid(self, **options: Any) -> None:
        self.grid_options = dict(options)

    def grid_forget(self) -> None:
        self.grid_options = {}

    def configure(self, **options: Any) -> None:
        self.options.update(options)

    config = configure

    def columnconfigure(self, index: int, *, weight: int) -> None:
        self.column_weights[index] = weight

    def rowconfigure(self, index: int, *, weight: int) -> None:
        self.row_weights[index] = weight

    def bind(self, sequence: str, handler: Any, add: str | None = None) -> str:
        identifier = f"{sequence}-{len(self.bindings.get(sequence, [])) + 1}"
        if add != "+":
            self.bindings[sequence] = []
        self.bindings.setdefault(sequence, []).append((identifier, handler))
        return identifier

    def unbind(self, sequence: str, identifier: str | None = None) -> None:
        if identifier is None:
            self.bindings.pop(sequence, None)
            return
        self.bindings[sequence] = [
            item for item in self.bindings.get(sequence, []) if item[0] != identifier
        ]

    def winfo_class(self) -> str:
        return self.widget_class


class FakeRoot(FakeWidget):
    widget_class = "Tk"

    def __init__(self) -> None:
        super().__init__()
        self.title_value = ""
        self.minimum_size = (0, 0)
        self.protocols: dict[str, Any] = {}
        self.cancelled: list[str] = []
        self.destroyed = False

    def title(self, value: str) -> None:
        self.title_value = value

    def minsize(self, width: int, height: int) -> None:
        self.minimum_size = (width, height)

    def protocol(self, name: str, callback: Any) -> None:
        self.protocols[name] = callback

    def after_cancel(self, identifier: str) -> None:
        self.cancelled.append(identifier)

    def destroy(self) -> None:
        self.destroyed = True

    def mainloop(self) -> None:
        pass


class FakeCanvas(FakeWidget):
    widget_class = "Canvas"

    def __init__(self, parent: Any = None, **options: Any) -> None:
        super().__init__(parent, **options)
        self.windows: dict[str, dict[str, Any]] = {}
        self.window_options: dict[str, dict[str, Any]] = {}
        self.scroll_calls: list[tuple[int, str]] = []
        self.move_calls: list[float] = []
        self.draw_calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.deleted: list[str] = []

    def create_window(self, coordinates: Any, **options: Any) -> str:
        identifier = f"window-{len(self.windows) + 1}"
        self.windows[identifier] = {"coordinates": coordinates, **options}
        return identifier

    def bbox(self, _tag: str) -> tuple[int, int, int, int]:
        return (0, 0, 900, 1800)

    def itemconfigure(self, identifier: str, **options: Any) -> None:
        self.window_options.setdefault(identifier, {}).update(options)

    def yview(self, *_args: Any) -> None:
        pass

    def yview_scroll(self, amount: int, unit: str) -> None:
        self.scroll_calls.append((amount, unit))

    def yview_moveto(self, fraction: float) -> None:
        self.move_calls.append(fraction)

    def delete(self, tag: str) -> None:
        self.deleted.append(tag)

    def _draw(self, name: str, *args: Any, **options: Any) -> str:
        self.draw_calls.append((name, args, options))
        return f"{name}-{len(self.draw_calls)}"

    def create_text(self, *args: Any, **options: Any) -> str:
        return self._draw("text", *args, **options)

    def create_image(self, *args: Any, **options: Any) -> str:
        return self._draw("image", *args, **options)

    def create_line(self, *args: Any, **options: Any) -> str:
        return self._draw("line", *args, **options)

    def create_rectangle(self, *args: Any, **options: Any) -> str:
        return self._draw("rectangle", *args, **options)

    def create_oval(self, *args: Any, **options: Any) -> str:
        return self._draw("oval", *args, **options)


class FakeScrollbar(FakeWidget):
    widget_class = "Scrollbar"

    def __init__(self, parent: Any = None, **options: Any) -> None:
        super().__init__(parent, **options)
        self.set_calls: list[tuple[Any, ...]] = []

    def set(self, *values: Any) -> None:
        self.set_calls.append(values)


class FakeText(FakeWidget):
    widget_class = "Text"

    def get(self, _start: str, _end: str) -> str:
        return "session-1,1,regular"


class FakeEntry(FakeWidget):
    widget_class = "Entry"


class FakeButton(FakeWidget):
    widget_class = "Button"


class FakePhotoImage:
    def __init__(self, **_options: Any) -> None:
        pass

    def subsample(self, _x: int, _y: int) -> FakePhotoImage:
        return self


class FakeTk:
    StringVar = FakeVariable
    Frame = FakeWidget
    LabelFrame = FakeWidget
    Label = FakeWidget
    Canvas = FakeCanvas
    Scrollbar = FakeScrollbar
    Entry = FakeEntry
    Text = FakeText
    Button = FakeButton
    PhotoImage = FakePhotoImage

    class OptionMenu(FakeWidget):
        def __init__(self, parent: Any, variable: Any, *values: Any, **options: Any) -> None:
            super().__init__(parent, variable, *values, **options)


@dataclass(frozen=True)
class FakeEvent:
    widget: Any
    width: int = 0
    delta: int = 0


def _view() -> tuple[TkOperatorView, FakeRoot]:
    root = FakeRoot()
    return TkOperatorView(root, FakeTk), root


def _is_descendant(widget: FakeWidget, ancestor: FakeWidget) -> bool:
    current: Any = widget
    while isinstance(current, FakeWidget):
        if current is ancestor:
            return True
        current = current.parent
    return False


def _walk_widgets(widget: FakeWidget) -> tuple[FakeWidget, ...]:
    descendants = [widget]
    for child in widget.children:
        descendants.extend(_walk_widgets(child))
    return tuple(descendants)


def test_root_content_uses_one_connected_vertical_scroll_area() -> None:
    view, _root = _view()

    assert isinstance(view._scroll_canvas, FakeCanvas)
    assert isinstance(view._scrollbar, FakeScrollbar)
    assert view._scrollbar.grid_options["sticky"] == "ns"
    assert view._scroll_content.parent is view._scroll_canvas
    embedded = view._scroll_canvas.windows[view._scroll_window_id]
    assert embedded["window"] is view._scroll_content
    assert embedded["anchor"] == "nw"
    assert view._scrollbar.options["command"].__self__ is view._scroll_canvas
    assert view._scroll_canvas.options["yscrollcommand"].__self__ is view._scrollbar


def test_scrollregion_and_content_width_follow_layout_changes() -> None:
    view, _root = _view()

    content_callback = view._scroll_content.bindings["<Configure>"][0][1]
    canvas_callback = view._scroll_canvas.bindings["<Configure>"][0][1]
    content_callback(FakeEvent(view._scroll_content))
    canvas_callback(FakeEvent(view._scroll_canvas, width=777))

    assert view._scroll_canvas.options["scrollregion"] == (0, 0, 900, 1800)
    assert view._scroll_canvas.window_options[view._scroll_window_id]["width"] == 777


def test_window_scrolling_is_bound_once_and_preserves_text_scrolling() -> None:
    view, root = _view()

    view._bind_scroll_navigation()
    assert len(root.bindings["<MouseWheel>"]) == 1
    assert all(len(root.bindings[sequence]) == 1 for sequence in view._scroll_binding_ids)

    mouse_handler = root.bindings["<MouseWheel>"][0][1]
    assert mouse_handler(FakeEvent(root, delta=-120)) == "break"
    assert view._scroll_canvas.scroll_calls == [(1, "units")]
    assert mouse_handler(FakeEvent(view._session_plan_widget, delta=-120)) is None
    assert view._scroll_canvas.scroll_calls == [(1, "units")]

    root.bindings["<Next>"][0][1](FakeEvent(root))
    root.bindings["<Home>"][0][1](FakeEvent(root))
    root.bindings["<End>"][0][1](FakeEvent(root))
    assert view._scroll_canvas.scroll_calls[-1] == (1, "pages")
    assert view._scroll_canvas.move_calls == [0.0, 1.0]


def test_all_operator_controls_and_preview_are_inside_scrollable_content() -> None:
    view, _root = _view()

    expected_labels = {
        OperatorAction.CONFIGURE_SOURCE: "Configure/Open Source",
        OperatorAction.START_PIPELINE: "Start Pipeline",
        OperatorAction.STOP_PIPELINE: "Stop Pipeline",
        OperatorAction.RESTART_VIDEO: "Restart Video",
        OperatorAction.REGISTER_TRUCK: "Register Truck",
        OperatorAction.START_TRUCK: "Start Truck",
        OperatorAction.START_SESSION: "Start Session",
        OperatorAction.COMPLETE_SESSION: "Complete Session",
        OperatorAction.CANCEL_SESSION: "Cancel Session",
        OperatorAction.COMPLETE_TRUCK: "Complete Truck",
        OperatorAction.CANCEL_TRUCK: "Cancel Truck",
        OperatorAction.REFRESH: "Refresh Snapshot",
        OperatorAction.EXIT: "Exit Application",
    }
    assert set(view._buttons) == set(OperatorAction)
    for action, label in expected_labels.items():
        assert view._buttons[action].options["text"] == label
        assert _is_descendant(view._buttons[action], view._scroll_content)
    assert _is_descendant(view._preview_canvas, view._scroll_content)
    assert view._preview_canvas.options["width"] == 400
    assert view._preview_canvas.options["height"] == 225


def test_wide_layout_prioritizes_preview_actions_and_compact_status() -> None:
    view, _root = _view()

    assert view._lane_panel.grid_options["row"] == 0
    assert view._lane_panel.grid_options["column"] == 0
    assert view._totals_panel.grid_options["row"] == 0
    assert view._totals_panel.grid_options["column"] == 1
    assert view._preview_panel.grid_options["row"] == 0
    assert view._preview_panel.grid_options["column"] == 0
    assert view._actions_panel.grid_options["row"] == 0
    assert view._actions_panel.grid_options["column"] == 1

    assert _is_descendant(
        view._buttons[OperatorAction.REGISTER_TRUCK],
        view._action_groups["truck_session"],
    )
    assert _is_descendant(
        view._buttons[OperatorAction.START_PIPELINE],
        view._action_groups["pipeline_source"],
    )
    assert _is_descendant(
        view._buttons[OperatorAction.EXIT],
        view._action_groups["application"],
    )
    pipeline_rows = {
        widget.grid_options["row"] for pair in view._pipeline_field_widgets for widget in pair
    }
    assert pipeline_rows == {1, 2}


def test_widget_dimensions_are_configured_on_widgets_not_grid() -> None:
    view, _root = _view()

    assert all("width" not in widget.grid_options for widget in _walk_widgets(view._scroll_content))


def test_docks_use_two_by_two_operational_order() -> None:
    view, _root = _view()

    assert view._dock_panels[DockId.DOCK_1].grid_options["row"] == 0
    assert view._dock_panels[DockId.DOCK_1].grid_options["column"] == 0
    assert view._dock_panels[DockId.DOCK_2].grid_options["row"] == 1
    assert view._dock_panels[DockId.DOCK_2].grid_options["column"] == 0
    assert view._dock_panels[DockId.DOCK_3].grid_options["row"] == 0
    assert view._dock_panels[DockId.DOCK_3].grid_options["column"] == 1
    assert view._dock_panels[DockId.DOCK_4].grid_options["row"] == 1
    assert view._dock_panels[DockId.DOCK_4].grid_options["column"] == 1


def test_narrow_layout_reflows_controls_without_horizontal_scroll() -> None:
    view, _root = _view()

    canvas_callback = view._scroll_canvas.bindings["<Configure>"][0][1]
    canvas_callback(FakeEvent(view._scroll_canvas, width=900))

    assert view._lane_panel.grid_options["columnspan"] == 2
    assert view._totals_panel.grid_options["row"] == 1
    assert view._actions_panel.grid_options["row"] == 0
    assert view._preview_panel.grid_options["row"] == 1
    pipeline_rows = {
        widget.grid_options["row"] for pair in view._pipeline_field_widgets for widget in pair
    }
    assert pipeline_rows == {1, 2, 3, 4}


def test_preview_empty_state_still_renders_inside_scrolled_layout() -> None:
    view, _root = _view()
    diagnostics = SimpleNamespace(
        preview_status="Waiting",
        preview_fps=0.0,
        preview_failures=0,
        pipeline_status="Stopped",
        camera_status="Closed",
    )

    view.render_preview(None, diagnostics)

    assert view._preview_canvas.deleted == ["all"]
    assert view._preview_canvas.draw_calls[-1][0] == "text"
    assert "Preview unavailable" in view._preview_canvas.draw_calls[-1][2]["text"]


def test_close_cancels_refresh_and_removes_owned_scroll_bindings() -> None:
    view, root = _view()
    view._live_refresh_after_id = "after-1"

    view.close()

    assert root.cancelled == ["after-1"]
    assert root.destroyed
    assert not view._scroll_binding_ids
    assert all(not handlers for handlers in root.bindings.values())
