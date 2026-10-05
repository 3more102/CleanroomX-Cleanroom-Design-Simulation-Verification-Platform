from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, Callable, Mapping

import tkinter as tk
from tkinter import ttk

from .gui_table import TreeviewTableBehavior
from .gui_theme import status_style_name, theme_palette


_TERMINAL_STATES = {
    "completed",
    "failed",
    "abandoned",
    "discarded",
    "cancelled",
}


def normalize_task_state(value: Any) -> str:
    token = str(value or "").strip().lower().replace("_", " ")
    aliases = {
        "success": "completed",
        "done": "completed",
        "error": "failed",
        "cancel requested": "abandon requested",
        "cancellation requested": "abandon requested",
    }
    token = aliases.get(token, token)
    allowed = {
        "queued",
        "running",
        "finalizing",
        "abandon requested",
        "completed",
        "failed",
        "abandoned",
        "discarded",
        "cancelled",
    }
    return token if token in allowed else "queued"


def task_state_style(value: Any) -> str:
    state = normalize_task_state(value)
    if state == "completed":
        return status_style_name("completed")
    if state == "failed":
        return status_style_name("failed")
    if state in {"running", "finalizing"}:
        return status_style_name("running")
    if state in {"abandon requested", "abandoned", "discarded", "cancelled"}:
        return status_style_name("warning")
    return status_style_name("unknown")


def execution_progress_label(value: Any) -> str:
    state = normalize_task_state(value)
    if state in {"running", "finalizing", "abandon requested"}:
        return "Indeterminate"
    if state == "completed":
        return "Complete"
    if state in {"failed", "abandoned", "discarded", "cancelled"}:
        return "Stopped"
    return "Not started"


def format_task_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    value = max(0.0, float(seconds))
    if value < 60.0:
        return f"{value:.1f} s"
    minutes, remainder = divmod(value, 60.0)
    if minutes < 60:
        return f"{int(minutes)}m {remainder:04.1f}s"
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours}h {minutes:02d}m"


@dataclass(frozen=True)
class TaskRecord:
    key: str
    name: str
    category: str
    state: str = "queued"
    stage: str = ""
    started_at: str = ""
    duration_seconds: float | None = None
    progress: str = "Not started"
    result: str = ""
    detail: str = ""

    @property
    def terminal(self) -> bool:
        return normalize_task_state(self.state) in _TERMINAL_STATES


class TaskCenter(ttk.Frame):
    """Session task center over real workstation operations.

    It is presentation-only. Operations without measurable backend progress are
    shown as Indeterminate until a terminal state is reported by the controller.
    """

    def __init__(
        self,
        master: tk.Misc,
        *,
        on_change: Callable[[int, int], None] | None = None,
        on_abandon: Callable[[str], bool] | None = None,
        table_layout: Mapping[str, Any] | None = None,
        on_table_layout_change: Callable[[dict[str, Any]], None] | None = None,
    ):
        super().__init__(master, padding=(8, 6))
        self._on_change = on_change or (lambda _active, _total: None)
        self._on_abandon = on_abandon
        self._table_layout = dict(table_layout or {})
        self._on_table_layout_change = on_table_layout_change
        self._records: dict[str, TaskRecord] = {}
        self._order: list[str] = []
        self.state_filter_var = tk.StringVar(value="All")
        self.summary_var = tk.StringVar(value="No workstation tasks in this session")
        self.detail_var = tk.StringVar(
            value="Select a task to inspect execution state and result details."
        )
        self._build()

    @property
    def records(self) -> tuple[TaskRecord, ...]:
        return tuple(self._records[key] for key in self._order if key in self._records)

    @property
    def active_count(self) -> int:
        return sum(1 for item in self._records.values() if not item.terminal)

    def _build(self) -> None:
        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(8, 6))
        header.pack(fill="x", pady=(0, 6))
        ttk.Label(
            header,
            text="JOB / TASK CENTER",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.summary_label = ttk.Label(
            header,
            textvariable=self.summary_var,
            style="CX.Status.Neutral.TLabel",
        )
        self.summary_label.pack(side="right")

        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(0, 6))
        ttk.Label(controls, text="State").pack(side="left", padx=(0, 5))
        self.state_filter = ttk.Combobox(
            controls,
            textvariable=self.state_filter_var,
            values=(
                "All",
                "Active",
                "Completed",
                "Failed",
                "Abandoned",
                "Discarded",
            ),
            state="readonly",
            width=14,
        )
        self.state_filter.pack(side="left")
        self.state_filter.bind("<<ComboboxSelected>>", lambda _event: self._refresh())
        ttk.Button(
            controls,
            text="Clear finished",
            style="CX.Compact.TButton",
            command=self.clear_finished,
        ).pack(side="right")
        self.abandon_button = ttk.Button(
            controls,
            text="Abandon selected",
            style="CX.Danger.TButton",
            command=self.abandon_selected,
            state="disabled",
        )
        self.abandon_button.pack(side="right", padx=(0, 6))

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True)

        table_host = ttk.Frame(body)
        detail_host = ttk.Frame(body, padding=(8, 6))
        body.add(table_host, weight=4)
        body.add(detail_host, weight=1)

        columns = (
            "category",
            "state",
            "progress",
            "started",
            "duration",
            "result",
        )
        self.tree = ttk.Treeview(
            table_host,
            columns=columns,
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Task")
        self.tree.heading("category", text="Category")
        self.tree.heading("state", text="State")
        self.tree.heading("progress", text="Progress")
        self.tree.heading("started", text="Started")
        self.tree.heading("duration", text="Duration")
        self.tree.heading("result", text="Result")
        self.tree.column("#0", width=260, minwidth=180)
        self.tree.column("category", width=110, stretch=False)
        self.tree.column("state", width=130, stretch=False)
        self.tree.column("progress", width=110, stretch=False)
        self.tree.column("started", width=95, stretch=False)
        self.tree.column("duration", width=90, stretch=False)
        self.tree.column("result", width=150, minwidth=100)
        self.table_behavior = TreeviewTableBehavior(
            self.tree,
            sortable_columns=("#0", "category", "state", "started", "result"),
            copy_columns=(
                "#0",
                "category",
                "state",
                "progress",
                "started",
                "duration",
                "result",
            ),
            layout_state=self._table_layout,
            on_layout_change=self._on_table_layout_change,
        )
        yscroll = ttk.Scrollbar(table_host, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_host, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_host.rowconfigure(0, weight=1)
        table_host.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._sync_detail)

        ttk.Label(
            detail_host,
            text="EXECUTION DETAILS",
            style="CX.Section.TLabel",
        ).pack(anchor="w")
        self.detail_label = ttk.Label(
            detail_host,
            textvariable=self.detail_var,
            justify="left",
            anchor="nw",
            wraplength=1000,
        )
        self.detail_label.pack(fill="both", expand=True, pady=(4, 0))
        self.apply_theme("dark")

    def apply_theme(self, theme: str) -> None:
        palette = theme_palette(theme)
        self.tree.tag_configure("task_pass", foreground=palette["success"])
        self.tree.tag_configure("task_fail", foreground=palette["error"])
        self.tree.tag_configure("task_warn", foreground=palette["warning"])
        self.tree.tag_configure("task_running", foreground=palette["simulation"])
        self.tree.tag_configure("task_neutral", foreground=palette["muted"])

    def start_task(
        self,
        key: str,
        name: str,
        *,
        category: str,
        stage: str = "Starting",
        started_at: str | None = None,
    ) -> TaskRecord:
        if key in self._records:
            raise ValueError(f"task already exists: {key}")
        record = TaskRecord(
            key=key,
            name=name,
            category=category,
            state="running",
            stage=stage,
            started_at=started_at
            or datetime.now().astimezone().strftime("%H:%M:%S"),
            duration_seconds=0.0,
            progress=execution_progress_label("running"),
        )
        self._records[key] = record
        self._order.append(key)
        self._refresh(select_key=key)
        return record

    def update_task(
        self,
        key: str,
        *,
        state: str | None = None,
        stage: str | None = None,
        duration_seconds: float | None = None,
        result: str | None = None,
        detail: str | None = None,
        progress: str | None = None,
    ) -> TaskRecord | None:
        record = self._records.get(key)
        if record is None:
            return None
        next_state = normalize_task_state(state if state is not None else record.state)
        next_progress = (
            progress
            if progress is not None
            else execution_progress_label(next_state)
        )
        updated = replace(
            record,
            state=next_state,
            stage=record.stage if stage is None else str(stage),
            duration_seconds=(
                record.duration_seconds
                if duration_seconds is None
                else max(0.0, float(duration_seconds))
            ),
            result=record.result if result is None else str(result),
            detail=record.detail if detail is None else str(detail),
            progress=next_progress,
        )
        self._records[key] = updated
        selected = self.tree.selection()
        selected_key = selected[0] if selected else None
        self._refresh(select_key=selected_key or key)
        return updated

    def abandon_selected(self) -> bool:
        selected = self.tree.selection()
        if not selected or self._on_abandon is None:
            return False
        record = self._records.get(selected[0])
        if record is None or record.terminal:
            return False
        if normalize_task_state(record.state) == "abandon requested":
            return False
        accepted = bool(self._on_abandon(record.key))
        self._sync_detail()
        return accepted

    def clear_finished(self) -> None:
        active = [
            key
            for key in self._order
            if key in self._records and not self._records[key].terminal
        ]
        self._records = {key: self._records[key] for key in active}
        self._order = active
        self._refresh()

    def _visible(self, record: TaskRecord) -> bool:
        selected = self.state_filter_var.get()
        state = normalize_task_state(record.state)
        if selected == "All":
            return True
        if selected == "Active":
            return state not in _TERMINAL_STATES
        return state == selected.lower()

    def _row_tag(self, state: str) -> str:
        token = normalize_task_state(state)
        if token == "completed":
            return "task_pass"
        if token == "failed":
            return "task_fail"
        if token in {"running", "finalizing"}:
            return "task_running"
        if token in {"abandon requested", "abandoned", "discarded", "cancelled"}:
            return "task_warn"
        return "task_neutral"

    def _refresh(self, *, select_key: str | None = None) -> None:
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for key in reversed(self._order):
            record = self._records.get(key)
            if record is None or not self._visible(record):
                continue
            self.tree.insert(
                "",
                "end",
                iid=record.key,
                text=record.name,
                values=(
                    record.category,
                    normalize_task_state(record.state).upper(),
                    record.progress,
                    record.started_at or "—",
                    format_task_duration(record.duration_seconds),
                    record.result or "—",
                ),
                tags=(self._row_tag(record.state),),
            )

        total = len(self._records)
        active = sum(1 for item in self._records.values() if not item.terminal)
        failed = sum(
            1 for item in self._records.values()
            if normalize_task_state(item.state) == "failed"
        )
        if total == 0:
            summary = "No workstation tasks in this session"
            style = "CX.Status.Neutral.TLabel"
        elif failed:
            summary = f"{active} active · {failed} failed · {total} total"
            style = "CX.Status.Fail.TLabel"
        elif active:
            summary = f"{active} active · {total} total"
            style = "CX.Status.Running.TLabel"
        else:
            summary = f"0 active · {total} completed/session"
            style = "CX.Status.Pass.TLabel"
        self.summary_var.set(summary)
        self.summary_label.configure(style=style)
        self._on_change(active, total)
        self.table_behavior.reapply_sort()

        if select_key and self.tree.exists(select_key):
            self.tree.selection_set(select_key)
            self.tree.focus(select_key)
            self.tree.see(select_key)
        self._sync_detail()

    def _sync_detail(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            self.abandon_button.configure(state="disabled")
            if self._records:
                self.detail_var.set(
                    "Select a task to inspect execution stage, duration, result, or failure details."
                )
            else:
                self.detail_var.set(
                    "No task has run in this session. Solver and long-running workstation "
                    "operations appear here when the controller starts them."
                )
            return
        record = self._records.get(selected[0])
        if record is None:
            self.abandon_button.configure(state="disabled")
            return
        can_abandon = (
            self._on_abandon is not None
            and not record.terminal
            and normalize_task_state(record.state) != "abandon requested"
        )
        self.abandon_button.configure(state="normal" if can_abandon else "disabled")
        lines = [
            f"{record.name}  ·  {record.category}",
            f"Execution state: {normalize_task_state(record.state).upper()}",
            f"Stage: {record.stage or '—'}",
            f"Progress: {record.progress}",
            f"Started: {record.started_at or '—'}",
            f"Duration: {format_task_duration(record.duration_seconds)}",
            f"Engineering/result status: {record.result or '—'}",
        ]
        if record.detail:
            lines.extend(("", record.detail))
        self.detail_var.set("\n".join(lines))
