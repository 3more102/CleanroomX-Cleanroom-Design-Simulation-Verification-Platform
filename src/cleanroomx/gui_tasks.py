from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
import time
from typing import Callable

import tkinter as tk
from tkinter import ttk


_FINAL_STATES = {"completed", "failed", "abandoned", "discarded"}


@dataclass(frozen=True)
class EngineeringTaskSnapshot:
    """Read-only presentation state for one engineering operation."""

    id: str
    name: str
    state: str
    detail: str
    started_at_utc: str
    elapsed_seconds: float
    result: str
    cancellable: bool

    @property
    def finished(self) -> bool:
        return self.state in _FINAL_STATES


@dataclass
class _EngineeringTask:
    id: str
    name: str
    state: str
    detail: str
    started_at_utc: str
    started_monotonic: float
    finished_monotonic: float | None = None
    result: str = ""
    cancellable: bool = False


class EngineeringTaskModel:
    """Small deterministic task ledger used by the GUI task center.

    The model records only application-observed task state. It never invents a
    completion percentage for backend operations that do not expose progress.
    """

    def __init__(
        self,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        utc_now: Callable[[], datetime] | None = None,
    ) -> None:
        self._monotonic = monotonic
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self._tasks: OrderedDict[str, _EngineeringTask] = OrderedDict()

    def start(
        self,
        task_id: str,
        name: str,
        *,
        detail: str = "",
        cancellable: bool = False,
    ) -> EngineeringTaskSnapshot:
        if not task_id:
            raise ValueError("task_id must not be empty")
        if task_id in self._tasks and self._tasks[task_id].state not in _FINAL_STATES:
            raise ValueError(f"task {task_id!r} is already active")
        started = self._utc_now().astimezone(timezone.utc)
        self._tasks[task_id] = _EngineeringTask(
            id=task_id,
            name=str(name).strip() or task_id,
            state="running",
            detail=str(detail).strip(),
            started_at_utc=started.isoformat().replace("+00:00", "Z"),
            started_monotonic=self._monotonic(),
            cancellable=bool(cancellable),
        )
        return self.snapshot(task_id)

    def mark_abandon_requested(
        self,
        task_id: str,
        detail: str = "Waiting for the backend worker to finish.",
    ) -> EngineeringTaskSnapshot:
        task = self._require(task_id)
        if task.state in _FINAL_STATES:
            return self.snapshot(task_id)
        task.state = "abandon_requested"
        task.detail = str(detail).strip() or task.detail
        return self.snapshot(task_id)

    def complete(self, task_id: str, result: str = "Completed") -> EngineeringTaskSnapshot:
        return self._finish(task_id, "completed", result)

    def fail(self, task_id: str, result: str) -> EngineeringTaskSnapshot:
        return self._finish(task_id, "failed", result)

    def abandon(self, task_id: str, result: str = "Result abandoned") -> EngineeringTaskSnapshot:
        return self._finish(task_id, "abandoned", result)

    def discard(self, task_id: str, result: str) -> EngineeringTaskSnapshot:
        return self._finish(task_id, "discarded", result)

    def remove_finished(self) -> int:
        before = len(self._tasks)
        self._tasks = OrderedDict(
            (task_id, task)
            for task_id, task in self._tasks.items()
            if task.state not in _FINAL_STATES
        )
        return before - len(self._tasks)

    def snapshots(self) -> tuple[EngineeringTaskSnapshot, ...]:
        return tuple(self._snapshot(task) for task in reversed(self._tasks.values()))

    def snapshot(self, task_id: str) -> EngineeringTaskSnapshot:
        return self._snapshot(self._require(task_id))

    def active_count(self) -> int:
        return sum(task.state not in _FINAL_STATES for task in self._tasks.values())

    def __len__(self) -> int:
        return len(self._tasks)

    def _finish(
        self,
        task_id: str,
        state: str,
        result: str,
    ) -> EngineeringTaskSnapshot:
        task = self._require(task_id)
        if task.finished_monotonic is None:
            task.finished_monotonic = self._monotonic()
        task.state = state
        task.result = str(result).strip()
        task.cancellable = False
        return self.snapshot(task_id)

    def _require(self, task_id: str) -> _EngineeringTask:
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise KeyError(f"unknown engineering task {task_id!r}") from exc

    def _snapshot(self, task: _EngineeringTask) -> EngineeringTaskSnapshot:
        end = (
            task.finished_monotonic
            if task.finished_monotonic is not None
            else self._monotonic()
        )
        elapsed = max(0.0, end - task.started_monotonic)
        return EngineeringTaskSnapshot(
            id=task.id,
            name=task.name,
            state=task.state,
            detail=task.detail,
            started_at_utc=task.started_at_utc,
            elapsed_seconds=elapsed,
            result=task.result,
            cancellable=task.cancellable and task.state == "running",
        )


class EngineeringTaskCenter(ttk.Frame):
    """Professional task/job surface for long-running engineering operations."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        status_setter: Callable[[str], None] | None = None,
        on_change: Callable[[int, int], None] | None = None,
    ) -> None:
        super().__init__(master)
        self.model = EngineeringTaskModel()
        self._status_setter = status_setter
        self._on_change = on_change
        self._cancel_callbacks: dict[str, Callable[[], None]] = {}
        self._refresh_after_id: str | None = None

        header = ttk.Frame(self, style="CX.PanelHeader.TFrame", padding=(8, 5))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="ENGINEERING TASK CENTER",
            style="CX.PanelHeader.TLabel",
        ).pack(side="left")
        self.summary_var = tk.StringVar(value="No active tasks")
        ttk.Label(
            header,
            textvariable=self.summary_var,
            style="CX.PanelHeader.TLabel",
        ).pack(side="right", padx=(8, 0))

        controls = ttk.Frame(self, padding=(6, 5))
        controls.pack(fill="x")
        self.abandon_button = ttk.Button(
            controls,
            text="Abandon selected",
            style="CX.Compact.TButton",
            command=self._abandon_selected,
            state="disabled",
        )
        self.abandon_button.pack(side="left")
        ttk.Button(
            controls,
            text="Clear finished",
            style="CX.Compact.TButton",
            command=self.clear_finished,
        ).pack(side="left", padx=(4, 0))
        ttk.Label(
            controls,
            text=(
                "Progress stays indeterminate when the backend does not expose a "
                "measured percentage."
            ),
            style="CX.Status.TLabel",
        ).pack(side="right")

        table_host = ttk.Frame(self)
        table_host.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.tree = ttk.Treeview(
            table_host,
            columns=("state", "started", "duration", "result"),
            show="tree headings",
            selectmode="browse",
        )
        self.tree.heading("#0", text="Task")
        self.tree.heading("state", text="State")
        self.tree.heading("started", text="Started (UTC)")
        self.tree.heading("duration", text="Duration")
        self.tree.heading("result", text="Result / failure")
        self.tree.column("#0", width=280, minwidth=160)
        self.tree.column("state", width=145, minwidth=110, stretch=False)
        self.tree.column("started", width=165, minwidth=135, stretch=False)
        self.tree.column("duration", width=90, minwidth=70, stretch=False)
        self.tree.column("result", width=420, minwidth=180)
        yscroll = ttk.Scrollbar(
            table_host,
            orient="vertical",
            command=self.tree.yview,
        )
        xscroll = ttk.Scrollbar(
            table_host,
            orient="horizontal",
            command=self.tree.xview,
        )
        self.tree.configure(
            yscrollcommand=yscroll.set,
            xscrollcommand=xscroll.set,
        )
        self.tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_host.rowconfigure(0, weight=1)
        table_host.columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self._on_selected)

        self.detail_var = tk.StringVar(
            value="Select a task to inspect its backend operation detail."
        )
        ttk.Label(
            self,
            textvariable=self.detail_var,
            style="CX.Status.TLabel",
            anchor="w",
            padding=(8, 4),
        ).pack(fill="x")
        self.bind("<Destroy>", self._on_destroy, add="+")

    def start_task(
        self,
        task_id: str,
        name: str,
        *,
        detail: str = "",
        cancellable: bool = False,
        cancel_callback: Callable[[], None] | None = None,
    ) -> EngineeringTaskSnapshot:
        if cancel_callback is not None:
            self._cancel_callbacks[task_id] = cancel_callback
            cancellable = True
        snapshot = self.model.start(
            task_id,
            name,
            detail=detail,
            cancellable=cancellable,
        )
        self._refresh()
        return snapshot

    def mark_abandon_requested(self, task_id: str, detail: str = "") -> None:
        self.model.mark_abandon_requested(
            task_id,
            detail or "Abandon requested; waiting for the backend worker to finish.",
        )
        self._refresh()

    def complete_task(self, task_id: str, result: str = "Completed") -> None:
        self.model.complete(task_id, result)
        self._cancel_callbacks.pop(task_id, None)
        self._refresh()

    def fail_task(self, task_id: str, result: str) -> None:
        self.model.fail(task_id, result)
        self._cancel_callbacks.pop(task_id, None)
        self._refresh()

    def abandon_task(self, task_id: str, result: str = "Result abandoned") -> None:
        self.model.abandon(task_id, result)
        self._cancel_callbacks.pop(task_id, None)
        self._refresh()

    def discard_task(self, task_id: str, result: str) -> None:
        self.model.discard(task_id, result)
        self._cancel_callbacks.pop(task_id, None)
        self._refresh()

    def clear_finished(self) -> None:
        removed = self.model.remove_finished()
        self._refresh()
        if self._status_setter is not None:
            self._status_setter(
                f"Task Center cleared {removed} finished task(s)"
                if removed
                else "Task Center has no finished tasks to clear"
            )

    def active_count(self) -> int:
        return self.model.active_count()

    def _refresh(self) -> None:
        snapshots = self.model.snapshots()
        selected = self.tree.selection()
        selected_id = selected[0] if selected else None

        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for task in snapshots:
            self.tree.insert(
                "",
                "end",
                iid=task.id,
                text=task.name,
                values=(
                    task.state.replace("_", " ").upper(),
                    _compact_utc(task.started_at_utc),
                    _format_duration(task.elapsed_seconds),
                    task.result or ("Working…" if not task.finished else ""),
                ),
            )

        if selected_id and self.tree.exists(selected_id):
            self.tree.selection_set(selected_id)
        self._on_selected()

        active = self.model.active_count()
        total = len(self.model)
        self.summary_var.set(
            f"{active} active · {total} retained"
            if total
            else "No active tasks"
        )
        if self._on_change is not None:
            self._on_change(active, total)

        if active:
            self._schedule_refresh()
        elif self._refresh_after_id is not None:
            try:
                self.after_cancel(self._refresh_after_id)
            except tk.TclError:
                pass
            self._refresh_after_id = None

    def _schedule_refresh(self) -> None:
        if self._refresh_after_id is None:
            self._refresh_after_id = self.after(500, self._refresh_tick)

    def _refresh_tick(self) -> None:
        self._refresh_after_id = None
        self._refresh()

    def _on_selected(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            self.detail_var.set("Select a task to inspect its backend operation detail.")
            self.abandon_button.configure(state="disabled")
            return
        task_id = selected[0]
        try:
            task = self.model.snapshot(task_id)
        except KeyError:
            return
        detail = task.detail or task.result or "No additional backend detail."
        self.detail_var.set(detail)
        self.abandon_button.configure(
            state=(
                "normal"
                if task.cancellable and task_id in self._cancel_callbacks
                else "disabled"
            )
        )

    def _abandon_selected(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        task_id = selected[0]
        callback = self._cancel_callbacks.get(task_id)
        if callback is None:
            return
        callback()
        try:
            self.mark_abandon_requested(task_id)
        except KeyError:
            pass

    def _on_destroy(self, event) -> None:
        if event.widget is not self:
            return
        if self._refresh_after_id is not None:
            try:
                self.after_cancel(self._refresh_after_id)
            except tk.TclError:
                pass
            self._refresh_after_id = None


def _format_duration(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    if seconds < 60.0:
        return f"{seconds:.1f} s"
    minutes, remainder = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes:d}m {remainder:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours:d}h {minutes:02d}m"


def _compact_utc(value: str) -> str:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1]
    return text.replace("T", " ")[:19]
