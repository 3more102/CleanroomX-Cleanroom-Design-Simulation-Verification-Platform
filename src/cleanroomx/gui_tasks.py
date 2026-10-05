from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import time
import tkinter as tk
from tkinter import ttk


_FINAL_STATES = {"completed", "failed", "abandoned", "discarded"}


@dataclass
class TaskRecord:
    id: str
    name: str
    state: str
    started_at_utc: str
    started_monotonic: float
    ended_monotonic: float | None = None
    progress: str = "Indeterminate"
    result: str = ""
    message: str = ""

    def duration_seconds(self, now: float | None = None) -> float:
        end = self.ended_monotonic
        if end is None:
            end = time.monotonic() if now is None else float(now)
        return max(0.0, end - self.started_monotonic)


def format_duration(seconds: float) -> str:
    total = max(0, int(round(float(seconds))))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


class TaskCenter(ttk.Frame):
    """Session-scoped UI for background work; never invents backend progress."""

    def __init__(self, parent: tk.Misc, *, status_setter=None):
        super().__init__(parent, padding=(8, 6))
        self._records: dict[str, TaskRecord] = {}
        self._order: list[str] = []
        self._status_setter = status_setter

        header = ttk.Frame(self)
        header.pack(fill="x", pady=(0, 6))
        ttk.Label(
            header,
            text="BACKGROUND TASKS",
            style="CX.Section.TLabel",
        ).pack(side="left")
        self.summary_var = tk.StringVar(value="No background tasks in this session.")
        ttk.Label(header, textvariable=self.summary_var).pack(side="right")

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(0, 6))
        ttk.Button(
            actions,
            text="Clear completed",
            style="CX.Compact.TButton",
            command=self.clear_finished,
        ).pack(side="right")

        body = ttk.Panedwindow(self, orient="vertical")
        body.pack(fill="both", expand=True)

        table_frame = ttk.Frame(body)
        body.add(table_frame, weight=3)
        self.tree = ttk.Treeview(
            table_frame,
            columns=("state", "progress", "started", "duration", "result"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Task")
        self.tree.heading("state", text="State")
        self.tree.heading("progress", text="Progress")
        self.tree.heading("started", text="Started (UTC)")
        self.tree.heading("duration", text="Duration")
        self.tree.heading("result", text="Result")
        self.tree.column("#0", width=260, minwidth=180)
        self.tree.column("state", width=95, stretch=False)
        self.tree.column("progress", width=110, stretch=False)
        self.tree.column("started", width=170, stretch=False)
        self.tree.column("duration", width=80, stretch=False, anchor="e")
        self.tree.column("result", width=260, minwidth=160)
        yscroll = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=yscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        detail_frame = ttk.Frame(body)
        body.add(detail_frame, weight=1)
        self.detail = tk.Text(detail_frame, height=7, wrap="word", state="disabled")
        detail_scroll = ttk.Scrollbar(
            detail_frame, orient="vertical", command=self.detail.yview
        )
        self.detail.configure(yscrollcommand=detail_scroll.set)
        self.detail.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

        self.tree.bind("<<TreeviewSelect>>", lambda event: self._show_selected_detail())

    def _set_detail(self, value: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", value)
        self.detail.configure(state="disabled")

    def _record_detail(self, record: TaskRecord) -> str:
        lines = [
            f"Task: {record.name}",
            f"State: {record.state.title()}",
            f"Progress: {record.progress}",
            f"Started (UTC): {record.started_at_utc}",
            f"Duration: {format_duration(record.duration_seconds())}",
        ]
        if record.result:
            lines.append(f"Result: {record.result}")
        if record.message:
            lines.extend(("", record.message))
        return "\n".join(lines) + "\n"

    def _show_selected_detail(self) -> None:
        selection = self.tree.selection()
        if not selection:
            self._set_detail("")
            return
        record = self._records.get(selection[0])
        self._set_detail(self._record_detail(record) if record is not None else "")

    def _refresh_summary(self) -> None:
        running = sum(
            1 for record in self._records.values() if record.state == "running"
        )
        finished = len(self._records) - running
        if not self._records:
            text = "No background tasks in this session."
        elif running:
            text = f"{running} running · {finished} finished"
        else:
            text = f"{finished} finished · none running"
        self.summary_var.set(text)

    def _upsert_row(self, record: TaskRecord) -> None:
        values = (
            record.state.title(),
            record.progress,
            record.started_at_utc.replace("T", " ")[:19],
            format_duration(record.duration_seconds()),
            record.result,
        )
        if self.tree.exists(record.id):
            self.tree.item(record.id, text=record.name, values=values)
        else:
            self.tree.insert("", "end", iid=record.id, text=record.name, values=values)

    def start_task(self, task_id: str, name: str, *, message: str = "") -> TaskRecord:
        if not task_id:
            raise ValueError("task_id must be non-empty")
        if task_id in self._records:
            raise ValueError(f"task already exists: {task_id}")
        record = TaskRecord(
            id=task_id,
            name=name,
            state="running",
            started_at_utc=datetime.now(timezone.utc).isoformat(),
            started_monotonic=time.monotonic(),
            message=message,
        )
        self._records[task_id] = record
        self._order.append(task_id)
        self._upsert_row(record)
        self.tree.selection_set(task_id)
        self.tree.focus(task_id)
        self.tree.see(task_id)
        self._show_selected_detail()
        self._refresh_summary()
        return record

    def mark_abandon_requested(self, task_id: str, message: str = "") -> None:
        record = self._records.get(task_id)
        if record is None or record.state != "running":
            return
        record.progress = "Abandon requested"
        if message:
            record.message = message
        self._upsert_row(record)
        self._show_selected_detail()
        self._refresh_summary()

    def finish_task(
        self,
        task_id: str,
        state: str,
        *,
        result: str = "",
        message: str = "",
    ) -> None:
        normalized = str(state).strip().casefold()
        if normalized not in _FINAL_STATES:
            raise ValueError(f"unsupported final task state: {state}")
        record = self._records.get(task_id)
        if record is None:
            return
        record.state = normalized
        record.ended_monotonic = time.monotonic()
        record.progress = "Complete"
        record.result = result
        if message:
            record.message = message
        self._upsert_row(record)
        self._show_selected_detail()
        self._refresh_summary()

    def refresh_elapsed(self) -> None:
        for task_id in self._order:
            record = self._records.get(task_id)
            if record is not None and record.state == "running":
                self._upsert_row(record)
        self._show_selected_detail()

    def running_count(self) -> int:
        return sum(
            1 for record in self._records.values() if record.state == "running"
        )

    def record(self, task_id: str) -> TaskRecord | None:
        return self._records.get(task_id)

    def clear_finished(self) -> None:
        for task_id in list(self._order):
            record = self._records.get(task_id)
            if record is None or record.state == "running":
                continue
            if self.tree.exists(task_id):
                self.tree.delete(task_id)
            self._order.remove(task_id)
            del self._records[task_id]
        self._show_selected_detail()
        self._refresh_summary()
        if self._status_setter is not None:
            self._status_setter("Finished task history cleared")
