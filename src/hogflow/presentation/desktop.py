"""Local desktop adapter for the snapshot-driven operator presentation."""

from __future__ import annotations

from typing import Any, Callable

from hogflow.application import (
    DockId,
    ExpectedOperatorError,
    OperatorApplication,
    OperatorInputError,
    PigType,
    PlannedSession,
    RegisterTruckCommand,
    VideoSourceRequest,
)
from hogflow.presentation.models import (
    CameraPipelinePanel,
    ConfirmationRequest,
    OperatorAction,
    OperatorScreen,
)
from hogflow.presentation.presenter import OperatorPresenter
from hogflow.presentation.preview import PreviewPrimitiveKind, PreviewRenderPlan

_EMPTY = "—"
_LIVE_REFRESH_INTERVAL_MS = 200


def parse_session_plan(value: str) -> tuple[PlannedSession, ...]:
    """Parse and validate newline-separated ``id,sequence,type[,expected]`` input."""

    if not isinstance(value, str):
        raise OperatorInputError("Session plan must be text.")
    rows = tuple(line.strip() for line in value.splitlines() if line.strip())
    if not rows:
        raise OperatorInputError("Register Truck requires at least one session row.")
    sessions: list[PlannedSession] = []
    session_ids: set[str] = set()
    sequences: set[int] = set()
    for row_number, row in enumerate(rows, start=1):
        fields = tuple(item.strip() for item in row.split(","))
        if len(fields) not in (3, 4):
            raise OperatorInputError(
                f"Session row {row_number} must use id,sequence,type[,expected]."
            )
        if not fields[0]:
            raise OperatorInputError(f"Session row {row_number} requires a session ID.")
        try:
            sequence_number = int(fields[1])
        except ValueError as exc:
            raise OperatorInputError(
                f"Session row {row_number} sequence must be a positive integer."
            ) from exc
        if sequence_number <= 0:
            raise OperatorInputError(
                f"Session row {row_number} sequence must be a positive integer."
            )
        try:
            pig_type = PigType.parse(fields[2].lower())
        except ExpectedOperatorError as exc:
            raise OperatorInputError(
                f"Session row {row_number} pig type must be regular, opg, p12, or nae."
            ) from exc
        try:
            expected_count = None
            if len(fields) == 4 and fields[3]:
                expected_count = int(fields[3])
            session = PlannedSession(
                session_id=fields[0],
                sequence_number=sequence_number,
                pig_type=pig_type,
                expected_count=expected_count,
            )
        except (ExpectedOperatorError, ValueError) as exc:
            raise OperatorInputError(f"Session row {row_number} is invalid.") from exc
        if session.session_id in session_ids:
            raise OperatorInputError(
                f"Session row {row_number} repeats session ID {session.session_id}."
            )
        if session.sequence_number in sequences:
            raise OperatorInputError(
                f"Session row {row_number} repeats sequence {session.sequence_number}."
            )
        session_ids.add(session.session_id)
        sequences.add(session.sequence_number)
        sessions.append(session)
    return tuple(sessions)


def parse_register_truck_form(
    dock_id: DockId,
    operation_id: str,
    session_plan: str,
) -> RegisterTruckCommand:
    """Validate the complete form before invoking the application service."""

    if not isinstance(operation_id, str) or not operation_id.strip():
        raise OperatorInputError("Register Truck requires an operation ID.")
    return RegisterTruckCommand(
        dock_id=DockId.parse(dock_id),
        operation_id=operation_id.strip(),
        sessions=parse_session_plan(session_plan),
    )


def parse_video_source_form(kind: str, value: str) -> VideoSourceRequest:
    """Validate a local camera index or video file before application invocation."""

    if kind == "camera":
        try:
            camera_index = int(value)
        except (TypeError, ValueError) as exc:
            raise OperatorInputError("Camera source requires a non-negative device index.") from exc
        return VideoSourceRequest.camera(camera_index)
    if kind == "video":
        if not isinstance(value, str) or not value.strip():
            raise OperatorInputError("Local video source requires an existing file.")
        return VideoSourceRequest.video_file(value.strip())
    raise OperatorInputError("Video source kind must be camera or video.")


class TkOperatorView:
    """Scrollable Tkinter adapter with snapshot-only business rendering."""

    def __init__(self, root: Any, tk: Any) -> None:
        self._root = root
        self._tk = tk
        self._presenter: OperatorPresenter | None = None
        self._dock_value = tk.StringVar(value=DockId.DOCK_1.value)
        self._operation_value = tk.StringVar(value="")
        self._session_value = tk.StringVar(value="")
        self._source_kind_value = tk.StringVar(value="camera")
        self._source_value = tk.StringVar(value="0")
        self._status_value = tk.StringVar(value="Ready")
        self._lane_values = {
            name: tk.StringVar(value=_EMPTY)
            for name in ("status", "dock", "truck", "pig_type", "session", "count")
        }
        self._dock_values = {dock: tk.StringVar(value="") for dock in DockId}
        self._totals_value = tk.StringVar(value="")
        self._pipeline_values = {
            name: tk.StringVar(value=_EMPTY)
            for name in (
                "source",
                "camera_status",
                "pipeline_status",
                "frames_acquired",
                "frames_processed",
                "fps",
                "temporary_failures",
                "stale",
                "worker",
                "recovery",
                "preview",
                "last_error",
                "lifecycle",
            )
        }
        self._preview_status_value = tk.StringVar(value="Preview Waiting")
        self._preview_canvas: Any = None
        self._preview_photo: Any = None
        self._live_refresh_after_id: Any = None
        self._closed = False
        self._session_plan_widget: Any = None
        self._buttons: dict[OperatorAction, Any] = {}
        self._scroll_binding_ids: dict[str, str | None] = {}
        self._scroll_canvas: Any = None
        self._scrollbar: Any = None
        self._scroll_content: Any = None
        self._scroll_window_id: Any = None
        self._build_layout()
        self._root.protocol("WM_DELETE_WINDOW", self._request_exit)

    def bind_presenter(self, presenter: OperatorPresenter) -> None:
        """Attach exactly one presenter at the composition boundary."""

        if not isinstance(presenter, OperatorPresenter):
            raise TypeError("Desktop view requires an OperatorPresenter.")
        if self._presenter is not None:
            raise RuntimeError("Desktop presenter is already bound.")
        self._presenter = presenter

    def start(self) -> None:
        """Render once, schedule one bounded UI refresh, and enter the toolkit loop."""

        self._require_presenter().refresh(self._dock())
        self._schedule_live_refresh()
        self._root.mainloop()

    def render(self, screen: OperatorScreen) -> None:
        """Replace widget output and control state from one immutable screen."""

        lane = screen.counting_lane
        values = (
            ("status", lane.status),
            ("dock", lane.current_dock),
            ("truck", lane.truck),
            ("pig_type", lane.pig_type),
            ("session", lane.current_session),
            ("count", str(lane.live_count)),
        )
        for key, value in values:
            self._lane_values[key].set(value)
        if hasattr(self, "_pipeline_values"):
            camera = screen.camera_pipeline
            pipeline_values = (
                ("source", camera.source),
                ("camera_status", camera.camera_status),
                ("pipeline_status", camera.pipeline_status),
                ("frames_acquired", str(camera.frames_acquired)),
                ("frames_processed", str(camera.frames_processed)),
                ("fps", f"{camera.effective_fps:.1f}"),
                ("temporary_failures", str(camera.temporary_failures)),
                ("stale", str(camera.stale_evidence_rejected)),
                ("worker", "Alive" if camera.worker_alive else "Stopped"),
                ("recovery", str(camera.recovery_attempts)),
                ("preview", camera.preview_status),
                ("last_error", camera.last_error),
                ("lifecycle", camera.active_crossing_lifecycle),
            )
            for key, value in pipeline_values:
                self._pipeline_values[key].set(value)
        for panel, dock in zip(screen.docks, DockId, strict=True):
            flags = tuple(
                value
                for value, enabled in (
                    ("SELECTED", panel.is_selected),
                    ("LANE OWNER", panel.owns_lane),
                )
                if enabled
            )
            heading = f" [{', '.join(flags)}]" if flags else ""
            self._dock_values[dock].set(
                "\n".join(
                    (
                        f"{panel.title}{heading}",
                        f"Operation ID: {panel.operation_id}",
                        f"Status: {panel.status}",
                        f"Pig Type: {panel.pig_type}",
                        f"Truck Total: {panel.truck_total}",
                        f"Current Session: {panel.current_session}",
                        f"Next Session: {panel.next_session}",
                        f"Next Pig Type: {panel.next_pig_type}",
                        f"Owns Shared Lane: {'YES' if panel.owns_lane else 'NO'}",
                    )
                )
            )
        selected = next(item for item in screen.docks if item.is_selected)
        if selected.current_session != _EMPTY:
            self._session_value.set(selected.current_session)
        elif selected.next_session != _EMPTY:
            self._session_value.set(selected.next_session)
        totals = screen.totals
        by_type = " | ".join(
            f"{pig_type}: {total}" for pig_type, total in totals.totals_by_pig_type
        )
        self._totals_value.set(
            f"Total pigs: {totals.total_pigs} | {by_type} | "
            f"Completed trucks: {totals.completed_trucks} | "
            f"Active trucks: {totals.active_trucks}"
        )
        for action, button in self._buttons.items():
            button.configure(state=("normal" if screen.actions.is_enabled(action) else "disabled"))
        self._status_value.set(screen.status_message)

    def render_preview(
        self,
        plan: PreviewRenderPlan | None,
        diagnostics: CameraPipelinePanel,
    ) -> None:
        """Render one latest frame on the UI thread only."""

        if self._preview_canvas is None:
            return
        self._preview_status_value.set(
            f"Preview: {diagnostics.preview_status} | "
            f"FPS: {diagnostics.preview_fps:.1f} | "
            f"Failures: {diagnostics.preview_failures}"
        )
        if plan is None:
            if diagnostics.pipeline_status in ("Stopped", "Failed"):
                self._preview_canvas.delete("all")
                self._preview_canvas.create_text(
                    12,
                    20,
                    anchor="nw",
                    text=(
                        f"Preview unavailable — camera {diagnostics.camera_status}; "
                        f"pipeline {diagnostics.pipeline_status}"
                    ),
                )
                self._preview_photo = None
            return
        photo = self._tk.PhotoImage(
            master=self._root,
            data=plan.ppm_data,
            format="PPM",
        )
        if plan.subsample > 1:
            photo = photo.subsample(plan.subsample, plan.subsample)
        canvas = self._preview_canvas
        canvas.configure(width=plan.display_width, height=plan.display_height)
        canvas.delete("all")
        canvas.create_image(0, 0, anchor="nw", image=photo)
        self._preview_photo = photo
        for primitive in plan.primitives:
            coordinates = primitive.coordinates
            if primitive.kind is PreviewPrimitiveKind.LINE:
                canvas.create_line(*coordinates, fill="#00ffff", width=2)
            elif primitive.kind is PreviewPrimitiveKind.RECTANGLE:
                canvas.create_rectangle(*coordinates, outline="#ffd200", width=2)
            elif primitive.kind is PreviewPrimitiveKind.POINT:
                x, y = coordinates
                canvas.create_oval(
                    x - 3,
                    y - 3,
                    x + 3,
                    y + 3,
                    fill="#ff00ff",
                    outline="#ff00ff",
                )
            else:
                canvas.create_text(
                    *coordinates,
                    anchor="nw",
                    text=primitive.text,
                    fill="white",
                )

    def show_error(self, message: str) -> None:
        """Expose an expected failure in the window and a modal dialog."""

        self._status_value.set(f"Error: {message}")
        from tkinter import messagebox

        messagebox.showerror("HogFlow", message, parent=self._root)

    def confirm(self, request: ConfirmationRequest) -> bool:
        """Ask the operator to acknowledge one destructive transition."""

        from tkinter import messagebox

        return bool(
            messagebox.askyesno(
                request.title,
                request.message,
                parent=self._root,
            )
        )

    def close(self) -> None:
        """Destroy the one local window after application shutdown."""

        self._closed = True
        if self._live_refresh_after_id is not None:
            self._root.after_cancel(self._live_refresh_after_id)
            self._live_refresh_after_id = None
        self._unbind_scroll_navigation()
        self._root.destroy()

    def _build_layout(self) -> None:
        tk = self._tk
        self._root.title("HogFlow Operator MVP")
        self._root.minsize(900, 600)
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(0, weight=1)

        outer = tk.Frame(self._root)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        self._scroll_canvas = tk.Canvas(
            outer,
            highlightthickness=0,
            borderwidth=0,
        )
        self._scroll_canvas.grid(row=0, column=0, sticky="nsew")
        self._scrollbar = tk.Scrollbar(
            outer,
            orient="vertical",
            command=self._scroll_canvas.yview,
        )
        self._scrollbar.grid(row=0, column=1, sticky="ns")
        self._scroll_canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scroll_content = tk.Frame(self._scroll_canvas)
        self._scroll_content.columnconfigure(0, weight=1)
        self._scroll_window_id = self._scroll_canvas.create_window(
            (0, 0),
            window=self._scroll_content,
            anchor="nw",
        )
        self._scroll_content.bind(
            "<Configure>",
            self._on_scroll_content_configure,
        )
        self._scroll_canvas.bind(
            "<Configure>",
            self._on_scroll_canvas_configure,
        )
        self._bind_scroll_navigation()

        lane = tk.LabelFrame(self._scroll_content, text="Shared Counting Lane")
        lane.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        lane_fields = (
            ("Status", "status"),
            ("Current Dock", "dock"),
            ("Truck", "truck"),
            ("Pig Type", "pig_type"),
            ("Current Session", "session"),
            ("Live Count", "count"),
        )
        for index, (label, key) in enumerate(lane_fields):
            row, column = divmod(index, 3)
            tk.Label(lane, text=f"{label}:").grid(row=row, column=column * 2, sticky="w")
            tk.Label(lane, textvariable=self._lane_values[key]).grid(
                row=row,
                column=column * 2 + 1,
                sticky="w",
                padx=(0, 12),
            )

        pipeline = tk.LabelFrame(self._scroll_content, text="Shared Camera Pipeline")
        pipeline.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        pipeline_fields = (
            ("Source", "source"),
            ("Camera", "camera_status"),
            ("Pipeline", "pipeline_status"),
            ("Acquired", "frames_acquired"),
            ("Processed", "frames_processed"),
            ("FPS", "fps"),
            ("Temporary", "temporary_failures"),
            ("Stale", "stale"),
            ("Worker", "worker"),
            ("Recovery", "recovery"),
            ("Preview", "preview"),
            ("Lifecycle", "lifecycle"),
            ("Last Error", "last_error"),
        )
        for index, (label, key) in enumerate(pipeline_fields):
            row, column = divmod(index, 4)
            tk.Label(pipeline, text=f"{label}:").grid(
                row=row,
                column=column * 2,
                sticky="w",
            )
            tk.Label(pipeline, textvariable=self._pipeline_values[key]).grid(
                row=row,
                column=column * 2 + 1,
                sticky="w",
                padx=(0, 12),
            )

        preview = tk.LabelFrame(self._scroll_content, text="Live Shared-Camera Preview")
        preview.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 8))
        preview.columnconfigure(0, weight=1)
        tk.Label(preview, textvariable=self._preview_status_value, anchor="w").grid(
            row=0,
            column=0,
            sticky="ew",
        )
        self._preview_canvas = tk.Canvas(
            preview,
            width=640,
            height=360,
            background="black",
            highlightthickness=0,
        )
        self._preview_canvas.grid(row=1, column=0, sticky="nsew")

        body = tk.Frame(self._scroll_content)
        body.grid(row=3, column=0, sticky="nsew", padx=8)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=1)

        docks = tk.LabelFrame(body, text="Docks")
        docks.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        docks.columnconfigure(0, weight=1)
        for row, dock in enumerate(DockId):
            panel = tk.LabelFrame(docks, text=f"Dock {dock.sequence_number}")
            panel.grid(row=row, column=0, sticky="ew", padx=6, pady=4)
            tk.Label(
                panel,
                textvariable=self._dock_values[dock],
                justify="left",
                anchor="w",
            ).grid(row=0, column=0, sticky="ew")

        actions = tk.LabelFrame(body, text="Operator Actions")
        actions.grid(row=0, column=1, sticky="nsew")
        actions.columnconfigure(1, weight=1)
        tk.Label(actions, text="Dock").grid(row=0, column=0, sticky="w")
        tk.OptionMenu(
            actions,
            self._dock_value,
            *(dock.value for dock in DockId),
            command=lambda _value: self._refresh_selected_dock(),
        ).grid(row=0, column=1, sticky="ew")
        tk.Label(actions, text="Operation ID").grid(row=1, column=0, sticky="w")
        tk.Entry(actions, textvariable=self._operation_value).grid(
            row=1,
            column=1,
            sticky="ew",
        )
        tk.Label(actions, text="Session plan").grid(row=2, column=0, sticky="nw")
        self._session_plan_widget = tk.Text(actions, width=34, height=5)
        self._session_plan_widget.grid(row=2, column=1, sticky="ew")
        tk.Label(actions, text="id,sequence,type[,expected]").grid(
            row=3,
            column=1,
            sticky="w",
        )
        tk.Label(actions, text="Session ID").grid(row=4, column=0, sticky="w")
        tk.Entry(actions, textvariable=self._session_value).grid(
            row=4,
            column=1,
            sticky="ew",
        )
        tk.Label(actions, text="Source").grid(row=5, column=0, sticky="w")
        source_frame = tk.Frame(actions)
        source_frame.grid(row=5, column=1, sticky="ew")
        source_frame.columnconfigure(1, weight=1)
        tk.OptionMenu(
            source_frame,
            self._source_kind_value,
            "camera",
            "video",
        ).grid(row=0, column=0, sticky="ew")
        tk.Entry(source_frame, textvariable=self._source_value).grid(
            row=0,
            column=1,
            sticky="ew",
        )

        callbacks: tuple[tuple[OperatorAction, str, Callable[[], None]], ...] = (
            (OperatorAction.REGISTER_TRUCK, "Register Truck", self._register_truck),
            (
                OperatorAction.START_TRUCK,
                "Start Truck",
                lambda: self._invoke(self._require_presenter().start_truck, self._dock()),
            ),
            (
                OperatorAction.START_SESSION,
                "Start Session",
                lambda: self._invoke(
                    self._require_presenter().start_session,
                    self._dock(),
                    self._session_value.get().strip(),
                ),
            ),
            (
                OperatorAction.COMPLETE_SESSION,
                "Complete Session",
                lambda: self._invoke(self._require_presenter().complete_session, self._dock()),
            ),
            (
                OperatorAction.CANCEL_SESSION,
                "Cancel Session",
                lambda: self._invoke(self._require_presenter().cancel_session, self._dock()),
            ),
            (
                OperatorAction.COMPLETE_TRUCK,
                "Complete Truck",
                lambda: self._invoke(self._require_presenter().complete_truck, self._dock()),
            ),
            (
                OperatorAction.CANCEL_TRUCK,
                "Cancel Truck",
                lambda: self._invoke(self._require_presenter().cancel_truck, self._dock()),
            ),
            (
                OperatorAction.CONFIGURE_SOURCE,
                "Configure/Open Source",
                self._configure_source,
            ),
            (
                OperatorAction.START_PIPELINE,
                "Start Pipeline",
                lambda: self._invoke(
                    self._require_presenter().start_counting_pipeline,
                    self._dock(),
                ),
            ),
            (
                OperatorAction.STOP_PIPELINE,
                "Stop Pipeline",
                lambda: self._invoke(
                    self._require_presenter().stop_counting_pipeline,
                    self._dock(),
                ),
            ),
            (
                OperatorAction.REFRESH,
                "Refresh Snapshot",
                self._refresh_selected_dock,
            ),
            (OperatorAction.EXIT, "Exit Application", self._request_exit),
        )
        for row, (action, label, callback) in enumerate(callbacks, start=6):
            button = tk.Button(actions, text=label, command=callback)
            button.grid(
                row=row,
                column=0,
                columnspan=2,
                sticky="ew",
                pady=2,
            )
            self._buttons[action] = button

        totals = tk.LabelFrame(self._scroll_content, text="Totals")
        totals.grid(row=4, column=0, sticky="ew", padx=8, pady=8)
        totals.columnconfigure(0, weight=1)
        tk.Label(totals, textvariable=self._totals_value, anchor="w").grid(
            row=0,
            column=0,
            sticky="ew",
        )
        tk.Label(self._scroll_content, textvariable=self._status_value, anchor="w").grid(
            row=5,
            column=0,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )

    def _on_scroll_content_configure(self, _event: Any) -> None:
        """Keep the vertical scroll range aligned with all rendered content."""

        bounds = self._scroll_canvas.bbox("all")
        if bounds is not None:
            self._scroll_canvas.configure(scrollregion=bounds)

    def _on_scroll_canvas_configure(self, event: Any) -> None:
        """Match the embedded content width to the visible viewport."""

        width = int(getattr(event, "width", 0))
        if width > 0:
            self._scroll_canvas.itemconfigure(self._scroll_window_id, width=width)

    def _bind_scroll_navigation(self) -> None:
        """Install one window-scoped mouse and keyboard navigation binding set."""

        if self._scroll_binding_ids:
            return
        handlers = {
            "<MouseWheel>": self._on_mouse_wheel,
            "<Up>": lambda event: self._scroll_by_units(event, -1),
            "<Down>": lambda event: self._scroll_by_units(event, 1),
            "<Prior>": lambda event: self._scroll_by_pages(event, -1),
            "<Next>": lambda event: self._scroll_by_pages(event, 1),
            "<Home>": lambda event: self._scroll_to_edge(event, 0.0),
            "<End>": lambda event: self._scroll_to_edge(event, 1.0),
        }
        self._scroll_binding_ids = {
            sequence: self._root.bind(sequence, handler, add="+")
            for sequence, handler in handlers.items()
        }

    def _unbind_scroll_navigation(self) -> None:
        """Remove only bindings owned by this view during deterministic shutdown."""

        for sequence, binding_id in self._scroll_binding_ids.items():
            if binding_id is not None:
                self._root.unbind(sequence, binding_id)
        self._scroll_binding_ids.clear()

    def _on_mouse_wheel(self, event: Any) -> str | None:
        """Scroll the Windows page and preserve multiline Text behavior."""

        if self._widget_class(event) == "Text":
            return None
        delta = int(getattr(event, "delta", 0))
        if delta == 0:
            return None
        units = -int(delta / 120)
        if units == 0:
            units = -1 if delta > 0 else 1
        self._scroll_canvas.yview_scroll(units, "units")
        return "break"

    def _scroll_by_units(self, event: Any, units: int) -> str | None:
        if self._uses_local_navigation(event):
            return None
        self._scroll_canvas.yview_scroll(units, "units")
        return "break"

    def _scroll_by_pages(self, event: Any, pages: int) -> str | None:
        if self._uses_local_navigation(event):
            return None
        self._scroll_canvas.yview_scroll(pages, "pages")
        return "break"

    def _scroll_to_edge(self, event: Any, fraction: float) -> str | None:
        if self._uses_local_navigation(event):
            return None
        self._scroll_canvas.yview_moveto(fraction)
        return "break"

    @staticmethod
    def _widget_class(event: Any) -> str:
        widget = getattr(event, "widget", None)
        if widget is None or not hasattr(widget, "winfo_class"):
            return ""
        return str(widget.winfo_class())

    @classmethod
    def _uses_local_navigation(cls, event: Any) -> bool:
        return cls._widget_class(event) in {
            "Entry",
            "Listbox",
            "Spinbox",
            "TEntry",
            "TSpinbox",
            "Text",
        }

    def _register_truck(self) -> None:
        try:
            command = parse_register_truck_form(
                self._dock(),
                self._operation_value.get(),
                self._session_plan_widget.get("1.0", "end"),
            )
            self._require_presenter().register_truck(command)
        except OperatorInputError as exc:
            self.show_error(str(exc))
        except ExpectedOperatorError:
            pass

    def _configure_source(self) -> None:
        try:
            request = parse_video_source_form(
                self._source_kind_value.get(),
                self._source_value.get(),
            )
            self._require_presenter().configure_video_source(request, self._dock())
        except OperatorInputError as exc:
            self.show_error(str(exc))
        except ExpectedOperatorError:
            pass

    def _refresh_selected_dock(self) -> None:
        self._invoke(self._require_presenter().refresh, self._dock())

    def _request_exit(self) -> None:
        self._invoke(self._require_presenter().request_exit, self._dock())

    def _schedule_live_refresh(self) -> None:
        if self._closed or self._live_refresh_after_id is not None:
            return
        self._live_refresh_after_id = self._root.after(
            _LIVE_REFRESH_INTERVAL_MS,
            self._run_live_refresh,
        )

    def _run_live_refresh(self) -> None:
        self._live_refresh_after_id = None
        if self._closed:
            return
        self._invoke(self._require_presenter().refresh, self._dock())
        self._schedule_live_refresh()

    def _dock(self) -> DockId:
        return DockId.parse(self._dock_value.get())

    def _require_presenter(self) -> OperatorPresenter:
        if self._presenter is None:
            raise RuntimeError("Desktop presenter must be bound before use.")
        return self._presenter

    @staticmethod
    def _invoke(action: Callable[..., Any], *args: Any) -> None:
        try:
            action(*args)
        except ExpectedOperatorError:
            pass


def create_tk_operator_view() -> TkOperatorView:
    """Create the local Tk adapter without composing business dependencies."""

    import tkinter as tk

    return TkOperatorView(tk.Tk(), tk)


def run_operator_desktop(application: OperatorApplication) -> None:
    """Compatibility composition for callers that already own an application."""

    view = create_tk_operator_view()
    presenter = OperatorPresenter(application, view)
    view.bind_presenter(presenter)
    view.start()


__all__ = [
    "TkOperatorView",
    "create_tk_operator_view",
    "parse_register_truck_form",
    "parse_session_plan",
    "parse_video_source_form",
    "run_operator_desktop",
]
