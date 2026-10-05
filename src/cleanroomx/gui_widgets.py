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
