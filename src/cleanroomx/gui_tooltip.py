from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class Tooltip:
    """Small delayed tooltip for engineering controls that need discoverability."""

    def __init__(self, widget: tk.Misc, text: str, *, delay_ms: int = 450) -> None:
        self.widget = widget
        self.text = str(text or "").strip()
        self.delay_ms = max(0, int(delay_ms))
        self._after_id: str | None = None
        self._window: tk.Toplevel | None = None

        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")
        widget.bind("<Destroy>", self._destroy, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel_schedule()
        if self.text:
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
        if not self.text or self._window is not None:
            return
        try:
            if not self.widget.winfo_exists():
                return
            pointer_x, pointer_y = self.widget.winfo_pointerxy()
        except tk.TclError:
            return

        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.attributes("-topmost", True)
        window.geometry(f"+{pointer_x + 14}+{pointer_y + 18}")
        frame = ttk.Frame(window, style="CX.Tooltip.TFrame", padding=(1, 1))
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=self.text,
            style="CX.Tooltip.TLabel",
            justify="left",
            wraplength=320,
        ).pack()
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

    def _destroy(self, _event=None) -> None:
        self._hide()


def attach_tooltip(
    widget: tk.Misc,
    text: str,
    *,
    delay_ms: int = 450,
) -> Tooltip:
    """Attach and retain a tooltip on a widget, returning it for tests/customization."""
    tooltip = Tooltip(widget, text, delay_ms=delay_ms)
    setattr(widget, "_cleanroomx_tooltip", tooltip)
    return tooltip
