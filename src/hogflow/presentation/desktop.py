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
from hogflow.presentation.theme import (
    HMI_THEME,
    OperatorMode,
    SemanticTone,
    operator_mode_for_source_type,
    semantic_tone_for_status,
)

_EMPTY = "—"
_LIVE_REFRESH_INTERVAL_MS = 200
_WIDE_LAYOUT_MINIMUM_WIDTH = 1100
_WIDE_PIPELINE_FIELD_COLUMNS = 7
_NARROW_PIPELINE_FIELD_COLUMNS = 4
_PREVIEW_INITIAL_WIDTH = 400
_PREVIEW_INITIAL_HEIGHT = 225


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
        self._mode_value = tk.StringVar(value=OperatorMode.VALIDATION_BUILD.value)
        self._system_state_value = tk.StringVar(value="SYSTEM READY")
        self._camera_state_value = tk.StringVar(value="CAMERA NOT CONFIGURED")
        self._pipeline_state_value = tk.StringVar(value="PIPELINE STOPPED")
        self._lane_values = {
            name: tk.StringVar(value=_EMPTY)
            for name in ("status", "dock", "truck", "pig_type", "session", "count")
        }
        self._dock_values = {dock: tk.StringVar(value="") for dock in DockId}
        self._totals_value = tk.StringVar(value="")
        self._total_metric_values = {
            name: tk.StringVar(value="0")
            for name in (
                "total_pigs",
                "completed_trucks",
                "active_trucks",
                "REGULAR",
                "OPG",
                "P-12",
                "NAE",
            )
        }
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
        self._button_style_options: dict[OperatorAction, dict[str, Any]] = {}
        self._scroll_binding_ids: dict[str, str | None] = {}
        self._scroll_canvas: Any = None
        self._scrollbar: Any = None
        self._scroll_content: Any = None
        self._scroll_window_id: Any = None
        self._layout_mode: tuple[bool, int] | None = None
        self._header_panel: Any = None
        self._mode_badge: Any = None
        self._system_state_widget: Any = None
        self._camera_state_widget: Any = None
        self._pipeline_state_widget: Any = None
        self._top_status_frame: Any = None
        self._lane_panel: Any = None
        self._lane_status_widget: Any = None
        self._lane_count_widget: Any = None
        self._pipeline_panel: Any = None
        self._pipeline_field_widgets: list[tuple[Any, Any]] = []
        self._pipeline_metric_widgets: dict[str, Any] = {}
        self._center_frame: Any = None
        self._preview_panel: Any = None
        self._actions_panel: Any = None
        self._action_groups: dict[str, Any] = {}
        self._docks_panel: Any = None
        self._dock_panels: dict[DockId, Any] = {}
        self._dock_labels: dict[DockId, Any] = {}
        self._totals_panel: Any = None
        self._totals_label: Any = None
        self._status_widget: Any = None
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
        camera = screen.camera_pipeline
        if hasattr(self, "_mode_value"):
            mode = operator_mode_for_source_type(camera.source_type)
            self._mode_value.set(mode.value)
            self._camera_state_value.set(f"CAMERA {camera.camera_status.upper()}")
            self._pipeline_state_value.set(f"PIPELINE {camera.pipeline_status.upper()}")
            system_status = self._system_status(camera)
            self._system_state_value.set(system_status)
            self._apply_header_visual_state(mode, camera, system_status)
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
        if hasattr(self, "_lane_status_widget") and self._lane_status_widget is not None:
            self._apply_status_tone(self._lane_status_widget, lane.status)
            self._lane_count_widget.configure(
                foreground=(
                    HMI_THEME.colors.accent
                    if lane.status == "Occupied"
                    else HMI_THEME.colors.text_primary
                )
            )
        if hasattr(self, "_pipeline_values"):
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
            for key, widget in self._pipeline_metric_widgets.items():
                status_value = self._pipeline_values[key].get()
                if key in {"camera_status", "pipeline_status", "worker", "preview"}:
                    self._apply_status_tone(widget, status_value)
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
                        f"Status: {panel.status}{heading} | Operation: {panel.operation_id}",
                        (
                            f"Pig Type: {panel.pig_type} | "
                            f"Current Session: {panel.current_session} | "
                            f"Truck Total: {panel.truck_total}"
                        ),
                        (
                            f"Next Session: {panel.next_session} ({panel.next_pig_type}) | "
                            f"Owns Shared Lane: {'YES' if panel.owns_lane else 'NO'}"
                        ),
                    )
                )
            )
            if hasattr(self, "_dock_labels") and dock in self._dock_labels:
                self._style_dock_panel(dock, panel.status, panel.is_selected, panel.owns_lane)
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
        if hasattr(self, "_total_metric_values"):
            self._total_metric_values["total_pigs"].set(f"{totals.total_pigs:,}")
            self._total_metric_values["completed_trucks"].set(str(totals.completed_trucks))
            self._total_metric_values["active_trucks"].set(str(totals.active_trucks))
            totals_by_type = dict(totals.totals_by_pig_type)
            for pig_type in ("REGULAR", "OPG", "P-12", "NAE"):
                self._total_metric_values[pig_type].set(f"{totals_by_type.get(pig_type, 0):,}")
        for action, button in self._buttons.items():
            enabled = screen.actions.is_enabled(action)
            if hasattr(self, "_button_style_options") and action in self._button_style_options:
                style = self._button_style_options[action]
                button.configure(
                    state=("normal" if enabled else "disabled"),
                    background=(style["background"] if enabled else HMI_THEME.colors.surface),
                    foreground=(style["foreground"] if enabled else HMI_THEME.colors.inactive),
                    activebackground=(
                        style["activebackground"] if enabled else HMI_THEME.colors.surface
                    ),
                    highlightbackground=(
                        HMI_THEME.colors.border_active if enabled else HMI_THEME.colors.border
                    ),
                )
            else:
                button.configure(state=("normal" if enabled else "disabled"))
        self._status_value.set(screen.status_message)
        if hasattr(self, "_status_widget") and self._status_widget is not None:
            self._apply_status_tone(self._status_widget, screen.status_message)

    @staticmethod
    def _system_status(camera: CameraPipelinePanel) -> str:
        camera_tone = semantic_tone_for_status(camera.camera_status)
        pipeline_tone = semantic_tone_for_status(camera.pipeline_status)
        if SemanticTone.CRITICAL in {camera_tone, pipeline_tone}:
            return "SYSTEM ATTENTION"
        if SemanticTone.WARNING in {camera_tone, pipeline_tone}:
            return "SYSTEM DEGRADED"
        if camera.pipeline_status == "Running" and camera.worker_alive:
            return "SYSTEM ACTIVE"
        return "SYSTEM READY"

    def _apply_header_visual_state(
        self,
        mode: OperatorMode,
        camera: CameraPipelinePanel,
        system_status: str,
    ) -> None:
        mode_tone = (
            SemanticTone.SUCCESS if mode is OperatorMode.LIVE_MODE else SemanticTone.INFORMATION
        )
        self._mode_badge.configure(foreground=HMI_THEME.tone_color(mode_tone))
        self._apply_status_tone(self._system_state_widget, system_status)
        self._apply_status_tone(self._camera_state_widget, camera.camera_status)
        self._apply_status_tone(self._pipeline_state_widget, camera.pipeline_status)

    @staticmethod
    def _apply_status_tone(widget: Any, status: str) -> None:
        widget.configure(foreground=HMI_THEME.tone_color(semantic_tone_for_status(status)))

    def _style_dock_panel(
        self,
        dock: DockId,
        status: str,
        selected: bool,
        owns_lane: bool,
    ) -> None:
        colors = HMI_THEME.colors
        panel = self._dock_panels[dock]
        label = self._dock_labels[dock]
        if owns_lane:
            background = "#12314A"
            border = colors.success
            foreground = colors.text_primary
        elif selected:
            background = colors.panel_elevated
            border = colors.accent
            foreground = colors.text_primary
        else:
            background = colors.panel
            border = colors.border
            foreground = colors.text_secondary
        panel.configure(
            background=background,
            foreground=(colors.success if owns_lane else colors.text_primary),
            highlightbackground=border,
        )
        label.configure(
            background=background,
            foreground=foreground,
        )
        if not owns_lane and not selected:
            self._apply_status_tone(panel, status)

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
                    fill=HMI_THEME.colors.text_secondary,
                    font=HMI_THEME.typography.font(HMI_THEME.typography.body_size),
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
                canvas.create_line(*coordinates, fill="#03101D", width=5)
                canvas.create_line(*coordinates, fill="#35D5E8", width=2)
            elif primitive.kind is PreviewPrimitiveKind.RECTANGLE:
                canvas.create_rectangle(*coordinates, outline=HMI_THEME.colors.warning, width=2)
            elif primitive.kind is PreviewPrimitiveKind.POINT:
                x, y = coordinates
                canvas.create_oval(
                    x - 3,
                    y - 3,
                    x + 3,
                    y + 3,
                    fill=HMI_THEME.colors.success,
                    outline="#07111F",
                )
            else:
                canvas.create_text(
                    *coordinates,
                    anchor="nw",
                    text=primitive.text,
                    fill=HMI_THEME.colors.text_primary,
                    font=HMI_THEME.typography.font(HMI_THEME.typography.micro_size, "bold"),
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
        colors = HMI_THEME.colors
        typography = HMI_THEME.typography
        spacing = HMI_THEME.spacing
        self._root.title("HogFlow — AI Livestock Receiving & Counting")
        self._root.minsize(900, 600)
        self._configure_initial_window_size()
        self._root.configure(background=colors.background)
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(0, weight=1)

        outer = tk.Frame(self._root, background=colors.background)
        outer.grid(row=0, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        self._scroll_canvas = tk.Canvas(
            outer,
            highlightthickness=0,
            borderwidth=0,
            background=colors.background,
        )
        self._scroll_canvas.grid(row=0, column=0, sticky="nsew")
        self._scrollbar = tk.Scrollbar(
            outer,
            orient="vertical",
            command=self._scroll_canvas.yview,
            background=colors.panel_elevated,
            troughcolor=colors.surface,
            activebackground=colors.accent,
        )
        self._scrollbar.grid(row=0, column=1, sticky="ns")
        self._scroll_canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scroll_content = tk.Frame(self._scroll_canvas, background=colors.background)
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

        self._header_panel = tk.Frame(
            self._scroll_content,
            background=colors.surface,
            highlightbackground=colors.border,
            highlightthickness=1,
        )
        self._header_panel.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=spacing.medium,
            pady=(spacing.medium, spacing.small),
        )
        self._header_panel.columnconfigure(0, weight=1)
        brand = tk.Frame(self._header_panel, background=colors.surface)
        brand.grid(row=0, column=0, sticky="w", padx=spacing.large, pady=spacing.small)
        tk.Label(
            brand,
            text="HogFlow",
            background=colors.surface,
            foreground=colors.text_primary,
            font=typography.font(typography.brand_size, "bold"),
        ).grid(row=0, column=0, sticky="w")
        tk.Label(
            brand,
            text="AI Livestock Receiving & Counting",
            background=colors.surface,
            foreground=colors.text_secondary,
            font=typography.font(typography.body_size),
        ).grid(row=1, column=0, sticky="w")

        global_status = tk.Frame(self._header_panel, background=colors.surface)
        global_status.grid(
            row=0,
            column=1,
            sticky="e",
            padx=spacing.large,
            pady=spacing.small,
        )
        header_items = (
            ("mode", self._mode_value),
            ("system", self._system_state_value),
            ("camera", self._camera_state_value),
            ("pipeline", self._pipeline_state_value),
        )
        for column, (name, variable) in enumerate(header_items):
            widget = tk.Label(
                global_status,
                textvariable=variable,
                background=colors.panel_elevated if name == "mode" else colors.surface,
                foreground=colors.information if name == "mode" else colors.text_secondary,
                font=typography.font(
                    typography.micro_size,
                    "bold" if name == "mode" else "normal",
                ),
                padx=spacing.medium,
                pady=spacing.small,
            )
            widget.grid(row=0, column=column, sticky="e", padx=(spacing.small, 0))
            if name == "mode":
                self._mode_badge = widget
            elif name == "system":
                self._system_state_widget = widget
            elif name == "camera":
                self._camera_state_widget = widget
            else:
                self._pipeline_state_widget = widget

        self._top_status_frame = tk.Frame(
            self._scroll_content,
            background=colors.background,
        )
        self._top_status_frame.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=spacing.medium,
            pady=spacing.xsmall,
        )
        self._top_status_frame.columnconfigure(0, weight=3)
        self._top_status_frame.columnconfigure(1, weight=2)

        self._lane_panel = tk.LabelFrame(
            self._top_status_frame,
            text="  SHARED COUNTING LANE  ",
            background=colors.panel,
            foreground=colors.text_primary,
            font=typography.font(typography.section_size, "bold"),
            highlightbackground=colors.border,
            highlightthickness=1,
            borderwidth=0,
            padx=spacing.medium,
            pady=spacing.small,
        )
        lane = self._lane_panel
        lane.columnconfigure(5, weight=1)
        self._lane_status_widget = tk.Label(
            lane,
            textvariable=self._lane_values["status"],
            background=colors.panel_elevated,
            foreground=colors.inactive,
            font=typography.font(typography.metric_size, "bold"),
            padx=spacing.medium,
            pady=spacing.small,
        )
        self._lane_status_widget.grid(
            row=0,
            column=0,
            sticky="nw",
            padx=(0, spacing.medium),
        )
        lane_fields = (
            ("DOCK", "dock"),
            ("OPERATION", "truck"),
            ("PIG TYPE", "pig_type"),
            ("SESSION", "session"),
        )
        for column, (label, key) in enumerate(lane_fields, start=1):
            field = tk.Frame(lane, background=colors.panel)
            field.grid(row=0, column=column, sticky="nw", padx=(0, spacing.large))
            tk.Label(
                field,
                text=label,
                background=colors.panel,
                foreground=colors.text_muted,
                font=typography.font(typography.micro_size, "bold"),
            ).grid(row=0, column=0, sticky="w")
            tk.Label(
                field,
                textvariable=self._lane_values[key],
                background=colors.panel,
                foreground=colors.text_primary,
                font=typography.font(typography.metric_size),
            ).grid(row=1, column=0, sticky="w")
        live_count = tk.Frame(lane, background=colors.panel)
        live_count.grid(row=0, column=6, sticky="e", padx=(spacing.medium, 0))
        tk.Label(
            live_count,
            text="LIVE COUNT",
            background=colors.panel,
            foreground=colors.text_secondary,
            font=typography.font(typography.micro_size, "bold"),
        ).grid(row=0, column=0, sticky="e")
        self._lane_count_widget = tk.Label(
            live_count,
            textvariable=self._lane_values["count"],
            background=colors.panel,
            foreground=colors.text_primary,
            font=typography.font(typography.live_count_size, "bold"),
        )
        self._lane_count_widget.grid(row=1, column=0, sticky="e")

        self._pipeline_panel = tk.LabelFrame(
            self._scroll_content,
            text="  SHARED CAMERA PIPELINE  ",
            background=colors.panel,
            foreground=colors.text_primary,
            font=typography.font(typography.section_size, "bold"),
            highlightbackground=colors.border,
            highlightthickness=1,
            borderwidth=0,
            padx=spacing.medium,
            pady=spacing.small,
        )
        pipeline = self._pipeline_panel
        pipeline.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=spacing.medium,
            pady=spacing.xsmall,
        )
        tk.Label(
            pipeline,
            text="SOURCE → DETECTOR → TRACKER → CROSSING → COUNTER → SHARED LANE",
            background=colors.panel,
            foreground=colors.information,
            font=typography.font(typography.micro_size, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=14, sticky="ew", pady=(0, spacing.small))
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
        pipeline_value_widths = (18, 12, 12, 7, 7, 6, 7, 6, 8, 7, 12, 16, 20)
        for (label, key), width in zip(
            pipeline_fields,
            pipeline_value_widths,
            strict=True,
        ):
            label_widget = tk.Label(pipeline, text=f"{label}:")
            value_widget = tk.Label(
                pipeline,
                textvariable=self._pipeline_values[key],
                anchor="w",
                width=width,
            )
            label_widget.configure(
                background=colors.panel,
                foreground=colors.text_muted,
                font=typography.font(typography.micro_size, "bold"),
            )
            value_widget.configure(
                background=colors.panel,
                foreground=colors.text_secondary,
                font=typography.font(typography.micro_size),
            )
            self._pipeline_field_widgets.append((label_widget, value_widget))
            self._pipeline_metric_widgets[key] = value_widget

        self._center_frame = tk.Frame(self._scroll_content, background=colors.background)
        self._center_frame.grid(
            row=3,
            column=0,
            sticky="nsew",
            padx=spacing.medium,
            pady=spacing.xsmall,
        )

        self._preview_panel = tk.LabelFrame(
            self._center_frame,
            text="  LIVE CAMERA · SHARED COUNTING CORRIDOR  ",
            background=colors.panel,
            foreground=colors.text_primary,
            font=typography.font(typography.section_size, "bold"),
            highlightbackground=colors.border_active,
            highlightthickness=1,
            borderwidth=0,
            padx=spacing.medium,
            pady=spacing.small,
        )
        preview = self._preview_panel
        preview.columnconfigure(0, weight=1)
        tk.Label(
            preview,
            textvariable=self._preview_status_value,
            anchor="w",
            background=colors.panel,
            foreground=colors.text_secondary,
            font=typography.font(typography.micro_size),
        ).grid(
            row=0,
            column=0,
            sticky="ew",
        )
        self._preview_canvas = tk.Canvas(
            preview,
            width=_PREVIEW_INITIAL_WIDTH,
            height=_PREVIEW_INITIAL_HEIGHT,
            background=colors.preview_background,
            highlightbackground=colors.border,
            highlightthickness=1,
            borderwidth=0,
        )
        self._preview_canvas.grid(row=1, column=0, sticky="nw")
        tk.Label(
            preview,
            text="Transient diagnostics · no video or frame history retained",
            anchor="w",
            background=colors.panel,
            foreground=colors.text_muted,
            font=typography.font(typography.micro_size),
        ).grid(row=2, column=0, sticky="ew", pady=(spacing.small, 0))

        body = tk.Frame(self._scroll_content, background=colors.background)
        body.grid(
            row=4,
            column=0,
            sticky="nsew",
            padx=spacing.medium,
            pady=spacing.xsmall,
        )
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        self._docks_panel = tk.LabelFrame(
            body,
            text="  DOCK OPERATIONS  ",
            background=colors.surface,
            foreground=colors.text_primary,
            font=typography.font(typography.section_size, "bold"),
            highlightbackground=colors.border,
            highlightthickness=1,
            borderwidth=0,
            padx=spacing.small,
            pady=spacing.small,
        )
        docks = self._docks_panel
        docks.grid(row=0, column=0, columnspan=2, sticky="nsew")
        docks.columnconfigure(0, weight=1)
        docks.columnconfigure(1, weight=1)
        dock_positions = {
            DockId.DOCK_1: (0, 0),
            DockId.DOCK_2: (1, 0),
            DockId.DOCK_3: (0, 1),
            DockId.DOCK_4: (1, 1),
        }
        for dock in DockId:
            row, column = dock_positions[dock]
            panel = tk.LabelFrame(
                docks,
                text=f"  DOCK {dock.sequence_number}  ",
                background=colors.panel,
                foreground=colors.text_primary,
                font=typography.font(typography.section_size, "bold"),
                highlightbackground=colors.border,
                highlightthickness=1,
                borderwidth=0,
                padx=spacing.medium,
                pady=spacing.xsmall,
            )
            panel.grid(
                row=row,
                column=column,
                sticky="nsew",
                padx=spacing.small,
                pady=spacing.small,
            )
            self._dock_panels[dock] = panel
            dock_label = tk.Label(
                panel,
                textvariable=self._dock_values[dock],
                justify="left",
                anchor="w",
                background=colors.panel,
                foreground=colors.text_secondary,
                font=typography.font(typography.body_size),
                padx=spacing.small,
                pady=spacing.xsmall,
            )
            dock_label.grid(row=0, column=0, sticky="ew")
            self._dock_labels[dock] = dock_label

        self._actions_panel = tk.LabelFrame(
            self._center_frame,
            text="  OPERATOR ACTIONS  ",
            background=colors.surface,
            foreground=colors.text_primary,
            font=typography.font(typography.section_size, "bold"),
            highlightbackground=colors.border,
            highlightthickness=1,
            borderwidth=0,
            padx=spacing.small,
            pady=spacing.small,
        )
        actions = self._actions_panel
        actions.columnconfigure(0, weight=3)
        actions.columnconfigure(1, weight=1)

        form = tk.Frame(actions, background=colors.surface)
        form.grid(row=0, column=0, columnspan=2, sticky="ew", padx=3, pady=2)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        field_label_options = {
            "background": colors.surface,
            "foreground": colors.text_secondary,
            "font": typography.font(typography.micro_size, "bold"),
        }
        field_options = {
            "background": colors.panel,
            "foreground": colors.text_primary,
            "activebackground": colors.panel_elevated,
            "activeforeground": colors.text_primary,
            "highlightbackground": colors.border,
            "font": typography.font(typography.body_size),
        }
        entry_options = {
            "background": colors.panel,
            "foreground": colors.text_primary,
            "insertbackground": colors.text_primary,
            "highlightbackground": colors.border,
            "highlightcolor": colors.focus,
            "highlightthickness": 1,
            "relief": "flat",
            "font": typography.font(typography.body_size),
        }
        tk.Label(form, text="DOCK", **field_label_options).grid(
            row=0,
            column=0,
            sticky="w",
        )
        dock_menu = tk.OptionMenu(
            form,
            self._dock_value,
            *(dock.value for dock in DockId),
            command=lambda _value: self._refresh_selected_dock(),
        )
        dock_menu.configure(**field_options)
        dock_menu.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        tk.Label(form, text="OPERATION ID", **field_label_options).grid(
            row=0,
            column=2,
            sticky="w",
        )
        tk.Entry(form, textvariable=self._operation_value, **entry_options).grid(
            row=0,
            column=3,
            sticky="ew",
        )
        tk.Label(form, text="SESSION ID", **field_label_options).grid(
            row=1,
            column=0,
            sticky="w",
        )
        tk.Entry(form, textvariable=self._session_value, **entry_options).grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(0, 4),
        )
        tk.Label(form, text="SESSION PLAN", **field_label_options).grid(
            row=1,
            column=2,
            sticky="nw",
        )
        self._session_plan_widget = tk.Text(form, width=26, height=2, **entry_options)
        self._session_plan_widget.grid(row=1, column=3, sticky="ew")
        tk.Label(
            form,
            text="id,sequence,type[,expected]",
            background=colors.surface,
            foreground=colors.text_muted,
            font=typography.font(typography.micro_size),
        ).grid(
            row=2,
            column=3,
            sticky="w",
        )

        group_options = {
            "background": colors.panel,
            "foreground": colors.text_secondary,
            "font": typography.font(typography.micro_size, "bold"),
            "highlightbackground": colors.border,
            "highlightthickness": 1,
            "borderwidth": 0,
            "padx": spacing.small,
            "pady": spacing.small,
        }
        truck_group = tk.LabelFrame(actions, text="  TRUCK / SESSION  ", **group_options)
        truck_group.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=3,
            pady=2,
        )
        for column in range(4):
            truck_group.columnconfigure(column, weight=1)
        self._action_groups["truck_session"] = truck_group

        pipeline_group = tk.LabelFrame(actions, text="  CAMERA / PIPELINE  ", **group_options)
        pipeline_group.grid(row=2, column=0, sticky="nsew", padx=3, pady=2)
        pipeline_group.columnconfigure(0, weight=1)
        pipeline_group.columnconfigure(1, weight=1)
        pipeline_group.columnconfigure(2, weight=1)
        pipeline_group.columnconfigure(3, weight=1)
        self._action_groups["pipeline_source"] = pipeline_group
        source_frame = tk.Frame(pipeline_group, background=colors.panel)
        source_frame.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 2))
        source_frame.columnconfigure(2, weight=1)
        tk.Label(
            source_frame,
            text="SOURCE",
            background=colors.panel,
            foreground=colors.text_muted,
            font=typography.font(typography.micro_size, "bold"),
        ).grid(row=0, column=0, sticky="w")
        source_menu = tk.OptionMenu(
            source_frame,
            self._source_kind_value,
            "camera",
            "video",
        )
        source_menu.configure(**field_options)
        source_menu.grid(row=0, column=1, sticky="ew")
        tk.Entry(source_frame, textvariable=self._source_value, **entry_options).grid(
            row=0,
            column=2,
            sticky="ew",
        )

        application_group = tk.LabelFrame(actions, text="  SYSTEM  ", **group_options)
        application_group.grid(row=2, column=1, sticky="nsew", padx=3, pady=2)
        application_group.columnconfigure(0, weight=1)
        application_group.columnconfigure(1, weight=1)
        self._action_groups["application"] = application_group

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
                OperatorAction.RESTART_VIDEO,
                "Restart Video",
                lambda: self._invoke(
                    self._require_presenter().restart_video,
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
        truck_positions = {
            OperatorAction.REGISTER_TRUCK: (0, 0),
            OperatorAction.START_TRUCK: (0, 1),
            OperatorAction.COMPLETE_TRUCK: (0, 2),
            OperatorAction.CANCEL_TRUCK: (0, 3),
            OperatorAction.START_SESSION: (1, 0),
            OperatorAction.COMPLETE_SESSION: (1, 1),
            OperatorAction.CANCEL_SESSION: (1, 2),
        }
        pipeline_positions = {
            OperatorAction.CONFIGURE_SOURCE: (1, 0),
            OperatorAction.START_PIPELINE: (1, 1),
            OperatorAction.STOP_PIPELINE: (1, 2),
            OperatorAction.RESTART_VIDEO: (1, 3),
        }
        application_positions = {
            OperatorAction.REFRESH: (0, 0),
            OperatorAction.EXIT: (0, 1),
        }
        for action, label, callback in callbacks:
            if action in truck_positions:
                parent = truck_group
                row, column = truck_positions[action]
                columnspan = 2 if action is OperatorAction.CANCEL_SESSION else 1
            elif action in pipeline_positions:
                parent = pipeline_group
                row, column = pipeline_positions[action]
                columnspan = 1
            else:
                parent = application_group
                row, column = application_positions[action]
                columnspan = 1
            button_options = self._button_options(action)
            self._button_style_options[action] = button_options
            button = tk.Button(
                parent,
                text=label,
                command=callback,
                **button_options,
            )
            button.grid(
                row=row,
                column=column,
                columnspan=columnspan,
                sticky="ew",
                padx=1,
                pady=1,
            )
            self._buttons[action] = button

        self._totals_panel = tk.LabelFrame(
            self._top_status_frame,
            text="  FINALIZED TOTALS  ",
            background=colors.panel,
            foreground=colors.text_primary,
            font=typography.font(typography.section_size, "bold"),
            highlightbackground=colors.border,
            highlightthickness=1,
            borderwidth=0,
            padx=spacing.medium,
            pady=spacing.small,
        )
        totals = self._totals_panel
        for column in range(4):
            totals.columnconfigure(column, weight=1)
        self._totals_label = tk.Label(
            totals,
            textvariable=self._totals_value,
            anchor="w",
            justify="left",
            background=colors.panel,
            foreground=colors.text_secondary,
        )
        total_layout = (
            ("TOTAL PIGS", "total_pigs", 0, 0, 2),
            ("COMPLETED TRUCKS", "completed_trucks", 0, 2, 1),
            ("ACTIVE TRUCKS", "active_trucks", 0, 3, 1),
            ("REGULAR", "REGULAR", 1, 0, 1),
            ("OPG", "OPG", 1, 1, 1),
            ("P-12", "P-12", 1, 2, 1),
            ("NAE", "NAE", 1, 3, 1),
        )
        for label, key, row, column, span in total_layout:
            metric = tk.Frame(totals, background=colors.panel_elevated)
            metric.grid(
                row=row,
                column=column,
                columnspan=span,
                sticky="nsew",
                padx=spacing.xsmall,
                pady=spacing.xsmall,
            )
            tk.Label(
                metric,
                text=label,
                background=colors.panel_elevated,
                foreground=colors.text_muted,
                font=typography.font(typography.micro_size, "bold"),
            ).grid(row=0, column=0, sticky="w", padx=(spacing.small, spacing.xsmall))
            tk.Label(
                metric,
                textvariable=self._total_metric_values[key],
                background=colors.panel_elevated,
                foreground=(colors.accent if key == "total_pigs" else colors.text_primary),
                font=typography.font(
                    typography.metric_size if key != "total_pigs" else 16,
                    "bold",
                ),
            ).grid(row=0, column=1, sticky="e", padx=(0, spacing.small))
            metric.columnconfigure(1, weight=1)

        status_panel = tk.Frame(
            self._scroll_content,
            background=colors.surface,
            highlightbackground=colors.border,
            highlightthickness=1,
        )
        status_panel.grid(
            row=5,
            column=0,
            sticky="ew",
            padx=spacing.medium,
            pady=(spacing.small, spacing.medium),
        )
        tk.Label(
            status_panel,
            text="OPERATOR STATUS",
            background=colors.surface,
            foreground=colors.text_muted,
            font=typography.font(typography.micro_size, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=spacing.medium, pady=spacing.small)
        self._status_widget = tk.Label(
            status_panel,
            textvariable=self._status_value,
            anchor="w",
            background=colors.surface,
            foreground=colors.information,
            font=typography.font(typography.body_size, "bold"),
        )
        self._status_widget.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(0, spacing.medium),
            pady=spacing.small,
        )
        status_panel.columnconfigure(1, weight=1)
        self._apply_responsive_layout(1366)

    def _configure_initial_window_size(self) -> None:
        """Use available desktop space without requiring maximization."""

        screen_width = getattr(self._root, "winfo_screenwidth", None)
        screen_height = getattr(self._root, "winfo_screenheight", None)
        geometry = getattr(self._root, "geometry", None)
        if not callable(screen_width) or not callable(screen_height) or not callable(geometry):
            return
        available_width = max(900, int(screen_width()) - 80)
        available_height = max(600, int(screen_height()) - 80)
        width = min(1600, available_width)
        height = min(920, available_height)
        geometry(f"{width}x{height}")

    @staticmethod
    def _button_options(action: OperatorAction) -> dict[str, Any]:
        colors = HMI_THEME.colors
        typography = HMI_THEME.typography
        destructive = action in {
            OperatorAction.CANCEL_SESSION,
            OperatorAction.CANCEL_TRUCK,
            OperatorAction.EXIT,
        }
        primary = action in {
            OperatorAction.START_TRUCK,
            OperatorAction.START_SESSION,
            OperatorAction.COMPLETE_SESSION,
            OperatorAction.START_PIPELINE,
        }
        if destructive:
            background = "#3A1F29"
            foreground = colors.critical
            active_background = "#522836"
        elif primary:
            background = colors.accent
            foreground = colors.text_primary
            active_background = colors.accent_hover
        else:
            background = colors.panel_elevated
            foreground = colors.text_primary
            active_background = colors.border
        return {
            "background": background,
            "foreground": foreground,
            "activebackground": active_background,
            "activeforeground": colors.text_primary,
            "disabledforeground": colors.inactive,
            "highlightbackground": colors.border,
            "highlightcolor": colors.focus,
            "highlightthickness": 1,
            "borderwidth": 0,
            "relief": "flat",
            "font": typography.font(typography.body_size, "bold"),
            "padx": HMI_THEME.spacing.medium,
            "pady": 3,
        }

    def _grid_pipeline_fields(self, field_columns: int) -> None:
        for index, (label_widget, value_widget) in enumerate(self._pipeline_field_widgets):
            field_row, field_column = divmod(index, field_columns)
            label_widget.grid(
                row=field_row + 1,
                column=field_column * 2,
                sticky="w",
                padx=(2, 1),
            )
            value_widget.grid(
                row=field_row + 1,
                column=field_column * 2 + 1,
                sticky="w",
                padx=(0, 3),
            )

    def _apply_responsive_layout(self, width: int) -> None:
        wide = width >= _WIDE_LAYOUT_MINIMUM_WIDTH
        pipeline_columns = _WIDE_PIPELINE_FIELD_COLUMNS if wide else _NARROW_PIPELINE_FIELD_COLUMNS
        layout_mode = (wide, pipeline_columns)
        if self._layout_mode == layout_mode:
            return
        self._layout_mode = layout_mode

        self._lane_panel.grid_forget()
        self._totals_panel.grid_forget()
        self._preview_panel.grid_forget()
        self._actions_panel.grid_forget()
        if wide:
            self._lane_panel.grid(row=0, column=0, sticky="ew", padx=(0, 2))
            self._totals_panel.grid(row=0, column=1, sticky="nsew", padx=(2, 0))
            self._center_frame.columnconfigure(0, weight=3)
            self._center_frame.columnconfigure(1, weight=2)
            self._preview_panel.grid(row=0, column=0, sticky="nw", padx=(0, 3))
            self._actions_panel.grid(row=0, column=1, sticky="new", padx=(3, 0))
            self._totals_label.configure(wraplength=max(280, int(width * 0.34)))
        else:
            self._lane_panel.grid(row=0, column=0, columnspan=2, sticky="ew")
            self._totals_panel.grid(
                row=1,
                column=0,
                columnspan=2,
                sticky="ew",
                pady=(2, 0),
            )
            self._center_frame.columnconfigure(0, weight=1)
            self._center_frame.columnconfigure(1, weight=0)
            self._actions_panel.grid(
                row=0,
                column=0,
                columnspan=2,
                sticky="ew",
                pady=(0, 3),
            )
            self._preview_panel.grid(
                row=1,
                column=0,
                columnspan=2,
                sticky="nw",
            )
            self._totals_label.configure(wraplength=max(400, width - 32))
        self._grid_pipeline_fields(pipeline_columns)

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
            self._apply_responsive_layout(width)

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
