from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any
import tkinter as tk
from tkinter import ttk

from .gui_theme import theme_palette


_TERMINAL_STATES = {
    "completed",
    "completed_with_warning",
    "failed",
    "abandoned",
    "discarded",
}


@dataclass(frozen=True)
class EngineeringTask:
    task_id: str
    name: str
    category: str
    state: str
    stage: str
    started_at: str
    elapsed_s: float = 0.0
    result: str = ""

    @property
    def terminal(self) -> bool:
        return self.state in _TERMINAL_STATES


def normalized_task_state(value: Any) -> str:
    token = str(value or "").strip().casefold().replace(" ", "_")
    aliases = {
        "success": "completed",
        "complete": "completed",
        "error": "failed",
        "cancelled": "abandoned",
        "canceled": "abandoned",
        "abandon_requested": "abandon_requested",
        "running": "running",
        "queued": "queued",
        "discarded": "discarded",
        "warning": "completed_with_warning",
    }
    normalized = aliases.get(token, token)
    return normalized if normalized else "queued"


def task_state_label(value: Any) -> str:
    state = normalized_task_state(value)
    return {
        "queued": "QUEUED",
        "running": "RUNNING",
        "abandon_requested": "ABANDON REQUESTED",
        "completed": "COMPLETED",
        "completed_with_warning": "COMPLETED · WARNING",
        "failed": "FAILED",
        "abandoned": "ABANDONED",
        "discarded": "DISCARDED",
    }.get(state, state.replace("_", " ").upper())


class EngineeringTaskCenter(ttk.Frame):
    """Current-session engineering job center backed only by real task events."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self._tasks: dict[str, EngineeringTask] = {}
        self._order: list[str] = []
        self._theme_name = "dark"
        self._palette = theme_palette(self._theme_name)
        self.summary_var = tk.StringVar(value="No engineering tasks in this session")
        self._build()

    def _build(self) -> None:
        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(7, 4))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="TASK CENTER",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            textvariable=self.summary_var,
            style="CX.ToolbarMuted.TLabel",
        ).pack(side="right")

        table_host = ttk.Frame(self)
        table_host.pack(fill="both", expand=True)
        columns = ("state", "task", "category", "stage", "elapsed", "result")
        self.tree = ttk.Treeview(
            table_host,
            columns=columns,
            show="headings",
            selectmode="browse",
            height=7,
        )
        headings = {
            "state": "State",
            "task": "Task",
            "category": "Type",
            "stage": "Current / Final stage",
            "elapsed": "Duration",
            "result": "Result",
        }
        widths = {
            "state": 150,
            "task": 220,
            "category": 110,
            "stage": 300,
            "elapsed": 90,
            "result": 240,
        }
        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=widths[column],
                minwidth=70,
                stretch=column in {"task", "stage", "result"},
            )

        yscroll = ttk.Scrollbar(table_host, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(table_host, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_host.rowconfigure(0, weight=1)
        table_host.columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self._show_detail)
        self._configure_tags()

        detail_host = ttk.Frame(self, style="CX.SubtlePanel.TFrame", padding=(7, 5))
        detail_host.pack(fill="x", padx=5, pady=(4, 5))
        self.detail = tk.Text(
            detail_host,
            wrap="word",
            height=4,
            state="disabled",
            borderwidth=0,
        )
        self.detail.pack(fill="x")

    def _configure_tags(self) -> None:
        palette = self._palette
        self.tree.tag_configure("running", foreground=palette["simulation"])
        self.tree.tag_configure("completed", foreground=palette["success"])
        self.tree.tag_configure("completed_with_warning", foreground=palette["warning"])
        self.tree.tag_configure("failed", foreground=palette["error"])
        self.tree.tag_configure("abandoned", foreground=palette["warning"])
        self.tree.tag_configure("discarded", foreground=palette["muted"])
        self.tree.tag_configure("abandon_requested", foreground=palette["attention"])
        self.tree.tag_configure("queued", foreground=palette["info"])

    def apply_theme(self, value: Any) -> None:
        self._theme_name = str(value or "dark")
        self._palette = theme_palette(self._theme_name)
        self._configure_tags()
        self.detail.configure(
            background=self._palette["field"],
            foreground=self._palette["field_text"],
            insertbackground=self._palette["text"],
            selectbackground=self._palette["selection"],
            selectforeground=self._palette["selection_text"],
        )

    @staticmethod
    def _started_text(value: str | None = None) -> str:
        if value:
            return str(value)
        return datetime.now().astimezone().strftime("%H:%M:%S")

    def start_task(
        self,
        task_id: str,
        *,
        name: str,
        category: str,
        stage: str = "Starting…",
        started_at: str | None = None,
    ) -> EngineeringTask:
        task = EngineeringTask(
            task_id=str(task_id),
            name=str(name),
            category=str(category),
            state="running",
            stage=str(stage),
            started_at=self._started_text(started_at),
        )
        self._tasks[task.task_id] = task
        if task.task_id in self._order:
            self._order.remove(task.task_id)
        self._order.insert(0, task.task_id)
        self._refresh()
        self.select_task(task.task_id)
        return task

    def update_task(
        self,
        task_id: str,
        *,
        state: str | None = None,
        stage: str | None = None,
        result: str | None = None,
        elapsed_s: float | None = None,
    ) -> EngineeringTask | None:
        key = str(task_id)
        current = self._tasks.get(key)
        if current is None:
            return None
        changes: dict[str, Any] = {}
        if state is not None:
            changes["state"] = normalized_task_state(state)
        if stage is not None:
            changes["stage"] = str(stage)
        if result is not None:
            changes["result"] = str(result)
        if elapsed_s is not None:
            changes["elapsed_s"] = max(0.0, float(elapsed_s))
        updated = replace(current, **changes)
        self._tasks[key] = updated
        self._refresh()
        return updated

    def finish_task(
        self,
        task_id: str,
        *,
        state: str,
        result: str = "",
        stage: str | None = None,
    ) -> EngineeringTask | None:
        normalized = normalized_task_state(state)
        if normalized not in _TERMINAL_STATES:
            raise ValueError(f"Task terminal state required, got {state!r}")
        return self.update_task(
            task_id,
            state=normalized,
            result=result,
            stage=stage,
        )

    def task(self, task_id: str) -> EngineeringTask | None:
        return self._tasks.get(str(task_id))

    def tasks(self) -> tuple[EngineeringTask, ...]:
        return tuple(
            self._tasks[task_id]
            for task_id in self._order
            if task_id in self._tasks
        )

    def select_task(self, task_id: str) -> bool:
        iid = f"task:{task_id}"
        if not self.tree.exists(iid):
            return False
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.tree.see(iid)
        self._show_detail()
        return True

    def _refresh(self) -> None:
        selection = self.tree.selection()
        selected = selection[0] if selection else ""
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        running = 0
        for task in self.tasks():
            if not task.terminal:
                running += 1
            iid = f"task:{task.task_id}"
            self.tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    task_state_label(task.state),
                    task.name,
                    task.category,
                    task.stage or "—",
                    f"{task.elapsed_s:.1f} s",
                    task.result or "—",
                ),
                tags=(task.state,),
            )
        total = len(self._tasks)
        if total:
            self.summary_var.set(
                f"{running} active · {total} session task{'s' if total != 1 else ''}"
            )
        else:
            self.summary_var.set("No engineering tasks in this session")
        if selected and self.tree.exists(selected):
            self.tree.selection_set(selected)
            self.tree.focus(selected)
        self._show_detail()

    def _show_detail(self, _event=None) -> None:
        selection = self.tree.selection()
        task = None
        if selection:
            task_id = selection[0].removeprefix("task:")
            task = self._tasks.get(task_id)
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        if task is None:
            self.detail.insert(
                "1.0",
                "No task selected. Analysis jobs started in this session will appear here.",
            )
        else:
            lines = [
                f"{task_state_label(task.state)}  |  {task.name}",
                f"Type: {task.category}",
                f"Started: {task.started_at}",
                f"Duration: {task.elapsed_s:.1f} s",
                f"Stage: {task.stage or '—'}",
            ]
            if task.result:
                lines.extend(("", "RESULT", task.result))
            self.detail.insert("1.0", "\n".join(lines))
        self.detail.configure(state="disabled")
