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
)
from hogflow.presentation.models import OperatorScreen
from hogflow.presentation.presenter import OperatorPresenter


def parse_session_plan(value: str) -> tuple[PlannedSession, ...]:
    """Parse newline-separated ``id,sequence,type[,expected]`` input."""

    if not isinstance(value, str):
        raise OperatorInputError("Session plan must be text.")
    rows = tuple(line.strip() for line in value.splitlines() if line.strip())
    if not rows:
        raise OperatorInputError("Register Truck requires at least one session row.")
    sessions: list[PlannedSession] = []
    for row_number, row in enumerate(rows, start=1):
        fields = tuple(item.strip() for item in row.split(","))
        if len(fields) not in (3, 4):
            raise OperatorInputError(
                f"Session row {row_number} must use id,sequence,type[,expected]."
            )
        try:
            sequence_number = int(fields[1])
            pig_type = PigType.parse(fields[2].lower())
            expected_count = None
            if len(fields) == 4 and fields[3]:
                expected_count = int(fields[3])
            sessions.append(
                PlannedSession(
                    session_id=fields[0],
                    sequence_number=sequence_number,
                    pig_type=pig_type,
                    expected_count=expected_count,
                )
            )
        except (ExpectedOperatorError, ValueError) as exc:
            raise OperatorInputError(f"Session row {row_number} is invalid.") from exc
    return tuple(sessions)


class TkOperatorView:
    """Unstyled Tkinter adapter with no business-state ownership."""

    def __init__(self, root: Any, tk: Any, application: OperatorApplication) -> None:
        self._root = root
        self._tk = tk
        self._application = application
        self._presenter = OperatorPresenter(application, self)
        self._dock_value = tk.StringVar(value=DockId.DOCK_1.value)
        self._operation_value = tk.StringVar(value="")
        self._session_value = tk.StringVar(value="")
        self._message_value = tk.StringVar(value="")
        self._lane_values = {
            name: tk.StringVar(value="—")
            for name in ("status", "dock", "truck", "pig_type", "session", "count")
        }
        self._dock_values = {dock: tk.StringVar(value="") for dock in DockId}
        self._totals_value = tk.StringVar(value="")
        self._session_plan_widget: Any = None
        self._build_layout()

    def start(self) -> None:
        """Render once and enter the toolkit loop without polling."""

        self._presenter.refresh()
        self._root.mainloop()

    def render(self, screen: OperatorScreen) -> None:
        """Replace widget text using one fresh immutable screen model."""

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
        for panel, dock in zip(screen.docks, DockId, strict=True):
            self._dock_values[dock].set(
                "\n".join(
                    (
                        f"Operation ID: {panel.operation_id}",
                        f"Status: {panel.status}",
                        f"Pig Type: {panel.pig_type}",
                        f"Truck Total: {panel.truck_total}",
                        f"Current Session: {panel.current_session}",
                    )
                )
            )
        totals = screen.totals
        by_type = " | ".join(
            f"{pig_type}: {total}" for pig_type, total in totals.totals_by_pig_type
        )
        self._totals_value.set(
            f"Total pigs: {totals.total_pigs} | {by_type} | "
            f"Completed trucks: {totals.completed_trucks} | "
            f"Active trucks: {totals.active_trucks}"
        )
        self._message_value.set(f"Snapshot: {screen.generated_at}")

    def show_error(self, message: str) -> None:
        """Expose an expected failure in the window and a modal dialog."""

        self._message_value.set(f"Error: {message}")
        from tkinter import messagebox

        messagebox.showerror("HogFlow", message, parent=self._root)

    def _build_layout(self) -> None:
        tk = self._tk
        self._root.title("HogFlow Operator MVP")
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(1, weight=1)

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

        body = tk.Frame(self._root)
        body.grid(row=1, column=0, sticky="nsew", padx=8)
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
        tk.OptionMenu(actions, self._dock_value, *(dock.value for dock in DockId)).grid(
            row=0,
            column=1,
            sticky="ew",
        )
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

        buttons: tuple[tuple[str, Callable[[], None]], ...] = (
            ("Register Truck", self._register_truck),
            ("Start Truck", lambda: self._invoke(self._presenter.start_truck, self._dock())),
            (
                "Start Session",
                lambda: self._invoke(
                    self._presenter.start_session,
                    self._dock(),
                    self._session_value.get().strip(),
                ),
            ),
            (
                "Complete Session",
                lambda: self._invoke(self._presenter.complete_session, self._dock()),
            ),
            (
                "Cancel Session",
                lambda: self._invoke(self._presenter.cancel_session, self._dock()),
            ),
            (
                "Complete Truck",
                lambda: self._invoke(self._presenter.complete_truck, self._dock()),
            ),
            (
                "Cancel Truck",
                lambda: self._invoke(self._presenter.cancel_truck, self._dock()),
            ),
            ("Refresh Snapshot", lambda: self._invoke(self._presenter.refresh)),
        )
        for row, (label, callback) in enumerate(buttons, start=5):
            tk.Button(actions, text=label, command=callback).grid(
                row=row,
                column=0,
                columnspan=2,
                sticky="ew",
                pady=2,
            )

        totals = tk.LabelFrame(self._root, text="Totals")
        totals.grid(row=2, column=0, sticky="ew", padx=8, pady=8)
        tk.Label(totals, textvariable=self._totals_value, anchor="w").grid(
            row=0,
            column=0,
            sticky="ew",
        )
        tk.Label(self._root, textvariable=self._message_value, anchor="w").grid(
            row=3,
            column=0,
            sticky="ew",
            padx=8,
            pady=(0, 8),
        )

    def _register_truck(self) -> None:
        try:
            command = RegisterTruckCommand(
                dock_id=self._dock(),
                operation_id=self._operation_value.get().strip(),
                sessions=parse_session_plan(self._session_plan_widget.get("1.0", "end")),
            )
            self._presenter.register_truck(command)
        except OperatorInputError as exc:
            self.show_error(str(exc))
        except ExpectedOperatorError:
            pass

    def _dock(self) -> DockId:
        return DockId.parse(self._dock_value.get())

    @staticmethod
    def _invoke(action: Callable[..., Any], *args: Any) -> None:
        try:
            action(*args)
        except ExpectedOperatorError:
            pass


def run_operator_desktop(application: OperatorApplication) -> None:
    """Run the local desktop adapter for an explicitly composed application."""

    import tkinter as tk

    root = tk.Tk()
    TkOperatorView(root, tk, application).start()


__all__ = ["TkOperatorView", "parse_session_plan", "run_operator_desktop"]
