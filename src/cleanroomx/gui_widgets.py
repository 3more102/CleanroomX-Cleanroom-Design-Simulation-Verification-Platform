from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ToolTip:
    """Small delayed tooltip for dense engineering controls."""

    def __init__(self, widget: tk.Misc, text: str, *, delay_ms: int = 450) -> None:
        self.widget = widget
        self.text = str(text)
        self.delay_ms = max(0, int(delay_ms))
        self._after_id: str | None = None
        self._window: tk.Toplevel | None = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<FocusOut>", self._hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel_schedule()
        self._after_id = self.widget.after(self.delay_ms, self._show)

    def _cancel_schedule(self) -> None:
        if self._after_id is None:
            return
        try:
            self.widget.after_cancel(self._after_id)
        except tk.TclError:
            pass
        self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if self._window is not None or not self.widget.winfo_exists():
            return
        try:
            x = self.widget.winfo_rootx() + 10
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 7
        except tk.TclError:
            return

        window = tk.Toplevel(self.widget)
        window.withdraw()
        window.overrideredirect(True)
        try:
            window.attributes("-topmost", True)
        except tk.TclError:
            pass
        label = ttk.Label(
            window,
            text=self.text,
            style="CX.Tooltip.TLabel",
            justify="left",
            wraplength=360,
            padding=(8, 5),
        )
        label.pack(fill="both", expand=True)
        window.geometry(f"+{x}+{y}")
        window.deiconify()
        self._window = window

    def _hide(self, _event=None) -> None:
        self._cancel_schedule()
        if self._window is None:
            return
        try:
            self._window.destroy()
        except tk.TclError:
            pass
        self._window = None


def attach_tooltip(widget: tk.Misc, text: str, *, delay_ms: int = 450) -> ToolTip:
    """Attach and retain one tooltip on a widget."""
    tooltip = ToolTip(widget, text, delay_ms=delay_ms)
    setattr(widget, "_cleanroomx_tooltip", tooltip)
    return tooltip



def engineering_sort_key(value) -> tuple[int, object]:
    """Sort engineering table values numerically when possible, otherwise naturally."""
    text = str(value if value is not None else "").strip()
    severity_rank = {
        "critical": 0,
        "error": 1,
        "fail": 1,
        "failed": 1,
        "warning": 2,
        "warn": 2,
        "stale": 3,
        "info": 4,
        "information": 4,
        "pass": 5,
        "passed": 5,
    }
    ranked = severity_rank.get(text.casefold())
    if ranked is not None:
        return (0, ranked)
    numeric_text = text.replace(",", "")
    try:
        return (1, float(numeric_text))
    except ValueError:
        return (2, text.casefold())


class TreeviewColumnSorter:
    """Reusable click-to-sort behavior for flat professional engineering tables."""

    def __init__(
        self,
        tree: ttk.Treeview,
        columns: tuple[str, ...] | list[str],
    ) -> None:
        self.tree = tree
        self.columns = tuple(columns)
        self._reverse: dict[str, bool] = {}
        self._base_headings: dict[str, str] = {}
        for column in self.columns:
            heading = str(tree.heading(column, "text"))
            self._base_headings[column] = heading
            tree.heading(
                column,
                command=lambda selected=column: self.sort(selected),
            )

    def sort(self, column: str) -> None:
        if column not in self.columns:
            return
        reverse = self._reverse.get(column, False)
        rows = list(self.tree.get_children(""))
        rows.sort(
            key=lambda iid: engineering_sort_key(
                self.tree.item(iid, "text")
                if column == "#0"
                else self.tree.set(iid, column)
            ),
            reverse=reverse,
        )
        for index, iid in enumerate(rows):
            self.tree.move(iid, "", index)

        for candidate, heading in self._base_headings.items():
            suffix = ""
            if candidate == column:
                suffix = " ▼" if reverse else " ▲"
            self.tree.heading(candidate, text=heading + suffix)
        self._reverse[column] = not reverse
