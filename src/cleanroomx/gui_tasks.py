from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable


_FINAL_STATES = {"completed", "failed", "abandoned"}


@dataclass
class TaskRecord:
    id: str
    name: str
    state: str
    progress: str
    started_at: str
    started_monotonic: float
    finished_monotonic: float | None = None
    result: str = ""
    message: str = ""

    def duration_seconds(self, now: float) -> float:
        end = self.finished_monotonic if self.finished_monotonic is not None else now
        return max(0.0, end - self.started_monotonic)


class TaskCenterPanel(ttk.Frame):
    """Read-only task history for GUI operations executed by background workers."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        status_setter: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(master)
        self._status_setter = status_setter or (lambda _message: None)
        self._clock = clock
        self._records: dict[str, TaskRecord] = {}
        self._detail_var = tk.StringVar(value="No background task selected")
        self._summary_var = tk.StringVar(value="Tasks: idle")

        header = ttk.Frame(self, padding=(7, 5))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="BACKGROUND TASKS",
            style="CX.Section.TLabel",
        ).pack(side="left")
        ttk.Label(
            header,
            textvariable=self._summary_var,
            anchor="e",
        ).pack(side="right", fill="x", expand=True)
        ttk.Button(
            header,
            text="Clear completed",
            style="CX.Compact.TButton",
            command=self.clear_completed,
        ).pack(side="right", padx=(6, 8))

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        columns = ("state", "progress", "started", "duration", "result")
        self.tree = ttk.Treeview(
            body,
            columns=columns,
            show="tree headings",
            selectmode="browse",
            height=7,
        )
        self.tree.heading("#0", text="Task")
        for column, label, width in (
            ("state", "State", 100),
            ("progress", "Progress", 95),
            ("started", "Started", 155),
            ("duration", "Duration", 90),
            ("result", "Result", 260),
        ):
            self.tree.heading(column, text=label)
            self.tree.column(
                column,
                width=width,
                minwidth=70,
                stretch=column == "result",
            )
        self.tree.column("#0", width=260, minwidth=160)
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._show_selected_detail)

        detail = ttk.Frame(self, padding=(7, 4))
        detail.pack(fill="x")
        ttk.Label(
            detail,
            textvariable=self._detail_var,
            anchor="w",
            justify="left",
            wraplength=1000,
        ).pack(fill="x")
        self.after(500, self._tick)

    @staticmethod
    def _state_label(state: str) -> str:
        return {
            "running": "Running",
            "completed": "Completed",
            "failed": "Failed",
            "abandoned": "Abandoned",
        }.get(state, state.title())

    def _row_values(self, record: TaskRecord) -> tuple[str, ...]:
        duration = record.duration_seconds(self._clock())
        return (
            self._state_label(record.state),
            record.progress or "—",
            record.started_at,
            f"{duration:.1f}s",
            record.result or record.message or "—",
        )

    def _upsert(self, record: TaskRecord) -> None:
        iid = record.id
        values = self._row_values(record)
        if self.tree.exists(iid):
            self.tree.item(iid, text=record.name, values=values)
        else:
            self.tree.insert(
                "",
                0,
                iid=iid,
                text=record.name,
                values=values,
            )
        self._refresh_summary()
        self._show_selected_detail()

    def start_task(
        self,
        task_id: str,
        name: str,
        *,
        progress: str = "Running",
    ) -> TaskRecord:
        if not task_id:
            raise ValueError("task_id must not be empty")
        if task_id in self._records and self._records[task_id].state not in _FINAL_STATES:
            raise ValueError(f"task is already active: {task_id}")
        record = TaskRecord(
            id=task_id,
            name=str(name or task_id),
            state="running",
            progress=str(progress or "Running"),
            started_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
            started_monotonic=self._clock(),
        )
        self._records[task_id] = record
        self._upsert(record)
        self.tree.selection_set(task_id)
        self.tree.focus(task_id)
        self._status_setter(f"Background task started: {record.name}")
        return record

    def update_task(
        self,
        task_id: str,
        *,
        progress: str | None = None,
        message: str | None = None,
    ) -> bool:
        record = self._records.get(task_id)
        if record is None or record.state in _FINAL_STATES:
            return False
        if progress is not None:
            record.progress = str(progress)
        if message is not None:
            record.message = str(message)
        self._upsert(record)
        return True

    def _finish(
        self,
        task_id: str,
        state: str,
        *,
        result: str = "",
        message: str = "",
    ) -> bool:
        record = self._records.get(task_id)
        if record is None or record.state in _FINAL_STATES:
            return False
        record.state = state
        record.progress = "100%" if state == "completed" else "—"
        record.result = str(result)
        record.message = str(message)
        record.finished_monotonic = self._clock()
        self._upsert(record)
        self._status_setter(
            f"Background task {self._state_label(state).lower()}: {record.name}"
        )
        return True

    def complete_task(self, task_id: str, *, result: str = "") -> bool:
        return self._finish(task_id, "completed", result=result)

    def fail_task(self, task_id: str, *, message: str) -> bool:
        return self._finish(task_id, "failed", message=message)

    def abandon_task(self, task_id: str, *, message: str = "") -> bool:
        return self._finish(task_id, "abandoned", message=message)

    def active_count(self) -> int:
        return sum(record.state not in _FINAL_STATES for record in self._records.values())

    def records(self) -> tuple[TaskRecord, ...]:
        return tuple(self._records.values())

    def clear_completed(self) -> None:
        for task_id, record in list(self._records.items()):
            if record.state not in _FINAL_STATES:
                continue
            self._records.pop(task_id, None)
            if self.tree.exists(task_id):
                self.tree.delete(task_id)
        self._refresh_summary()
        self._show_selected_detail()
        self._status_setter("Completed background task history cleared")

    def _refresh_summary(self) -> None:
        active = self.active_count()
        failed = sum(record.state == "failed" for record in self._records.values())
        self._summary_var.set(
            f"Tasks: {active} active · {failed} failed · {len(self._records)} retained"
            if self._records
            else "Tasks: idle"
        )

    def _show_selected_detail(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            self._detail_var.set("No background task selected")
            return
        record = self._records.get(selection[0])
        if record is None:
            self._detail_var.set("No background task selected")
            return
        detail = (
            f"{record.name} · {self._state_label(record.state)} · "
            f"{record.duration_seconds(self._clock()):.1f}s"
        )
        if record.message:
            detail += f" · {record.message}"
        elif record.result:
            detail += f" · {record.result}"
        self._detail_var.set(detail)

    def _tick(self) -> None:
        if not self.winfo_exists():
            return
        for record in self._records.values():
            if record.state == "running":
                self._upsert(record)
        self.after(500, self._tick)
