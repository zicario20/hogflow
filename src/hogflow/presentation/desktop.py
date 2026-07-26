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
    ConfirmationRequest,
    OperatorAction,
    OperatorScreen,
)
from hogflow.presentation.presenter import OperatorPresenter

_EMPTY = "—"


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
    """Unstyled Tkinter adapter with snapshot-only business rendering."""

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
                "last_error",
                "lifecycle",
            )
        }
        self._session_plan_widget: Any = None
        self._buttons: dict[OperatorAction, Any] = {}
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
        """Render once and enter the toolkit loop without polling."""

        self._require_presenter().refresh(self._dock())
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

        self._root.destroy()

    def _build_layout(self) -> None:
        tk = self._tk
        self._root.title("HogFlow Operator MVP")
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(2, weight=1)

        lane = tk.LabelFrame(self._root, text="Shared Counting Lane")
        lane.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        lane_fields = (
            ("Status", "status"),
            ("Current Dock", "dock"),
            ("Truck", "truck"),
            ("Pig Type", "pig_type"),
            ("Current Session", "session"),
            ("Live Count", "count"),
        )
        for column, (label, key) in enumerate(lane_fields):
            tk.Label(lane, text=f"{label}:").grid(row=0, column=column * 2, sticky="w")
            tk.Label(lane, textvariable=self._lane_values[key]).grid(
                row=0,
                column=column * 2 + 1,
                sticky="w",
                padx=(0, 12),
            )

        pipeline = tk.LabelFrame(self._root, text="Shared Camera Pipeline")
        pipeline.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        pipeline_fields = (
            ("Source", "source"),
            ("Camera", "camera_status"),
            ("Pipeline", "pipeline_status"),
            ("Acquired", "frames_acquired"),
            ("Processed", "frames_processed"),
            ("Lifecycle", "lifecycle"),
            ("Last Error", "last_error"),
        )
        for column, (label, key) in enumerate(pipeline_fields):
            tk.Label(pipeline, text=f"{label}:").grid(
                row=0,
                column=column * 2,
                sticky="w",
            )
            tk.Label(pipeline, textvariable=self._pipeline_values[key]).grid(
                row=0,
                column=column * 2 + 1,
                sticky="w",
                padx=(0, 12),
            )

        body = tk.Frame(self._root)
        body.grid(row=2, column=0, sticky="nsew", padx=8)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=1)

        docks = tk.LabelFrame(body, text="Docks")
        docks.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
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

        totals = tk.LabelFrame(self._root, text="Totals")
        totals.grid(row=3, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(totals, textvariable=self._totals_value, anchor="w").grid(
            row=0,
            column=0,
            sticky="ew",
        )
        tk.Label(self._root, textvariable=self._status_value, anchor="w").grid(
            row=4,
            column=0,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )

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
