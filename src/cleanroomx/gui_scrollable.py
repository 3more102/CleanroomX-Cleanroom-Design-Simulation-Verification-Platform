"""Locally scoped, two-axis scrolling for dense CleanroomX notebook tabs.

Presentation canvases (charts/plots) are treated as scrollable tab content.
Interactive canvases with explicit wheel bindings or scrollbar commands keep
their own wheel handling. Never bind events globally.

Only Tk presentation is affected; CFD calculations, solver outputs, and
engineering/validation metadata remain untouched.
"""
from __future__ import annotations

import tkinter as tk
import weakref
from tkinter import ttk


_NATIVE_WHEEL = (tk.Text, tk.Listbox, tk.Scale,
                 ttk.Treeview, ttk.Combobox, ttk.Scrollbar, ttk.Scale)
_WHEEL_EVENTS = ("<MouseWheel>", "<Shift-MouseWheel>",
                 "<Button-4>", "<Button-5>",
                 "<Shift-Button-4>", "<Shift-Button-5>")


def _owns_wheel(widget: tk.Misc) -> bool:
    """Preserve controls with native scrolling and Canvas custom zoom handlers."""
    if isinstance(widget, _NATIVE_WHEEL):
        return True
    if isinstance(widget, tk.Canvas):
        # A chart bound by this tab remains a plain presentation canvas.
        # Do not mistake our own wheel callback for an application zoom handler.
        if getattr(widget, "_cleanroomx_tab_wheel_binding", False):
            return False
        return (bool(widget.cget("yscrollcommand"))
                or bool(widget.cget("xscrollcommand"))
                or any(bool(widget.bind(sequence)) for sequence in _WHEEL_EVENTS))
    return False


def create_scrollable_content(host: ttk.Frame, *, padding: int = 10) -> ttk.Frame:
    """Create a scrollable tab body and return the frame for its contents.

    Bind only this tab and its descendants (never Tk's global bind_all).
    Descendants inserted later become scrollable on content geometry updates.
    """
    host.rowconfigure(0, weight=1)
    host.columnconfigure(0, weight=1)
    background = ttk.Style(host).lookup("TFrame", "background") or "#f0f0f0"
    canvas = tk.Canvas(host, borderwidth=0, highlightthickness=0,
                       background=background, takefocus=1)
    vertical = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
    horizontal = ttk.Scrollbar(host, orient="horizontal", command=canvas.xview)
    canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    canvas.grid(row=0, column=0, sticky="nsew")
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal.grid(row=1, column=0, sticky="ew")
    content = ttk.Frame(canvas, padding=padding)
    content_id = canvas.create_window((0, 0), window=content, anchor="nw")
    registered = weakref.WeakSet()

    def on_vertical(event):
        if event.delta:
            direction = -1 if event.delta > 0 else 1
            units = max(1, abs(event.delta) // 120)
            canvas.yview_scroll(direction * units, "units")
            return "break"
        return None

    def on_horizontal(event):
        if event.delta:
            direction = -1 if event.delta > 0 else 1
            units = max(1, abs(event.delta) // 120)
            canvas.xview_scroll(direction * units, "units")
            return "break"
        return None

    def linux_wheel(axis: str, direction: int):
        def callback(_event):
            if axis == "x":
                canvas.xview_scroll(direction, "units")
            else:
                canvas.yview_scroll(direction, "units")
            return "break"
        return callback

    def register_descendants(widget):
        for child in widget.winfo_children():
            if child not in registered:
                if _owns_wheel(child):
                    continue
                registered.add(child)
                if isinstance(child, tk.Canvas):
                    child._cleanroomx_tab_wheel_binding = True
                child.bind("<MouseWheel>", on_vertical, add="+")
                child.bind("<Shift-MouseWheel>", on_horizontal, add="+")
                child.bind("<Button-4>", linux_wheel("y", -1), add="+")
                child.bind("<Button-5>", linux_wheel("y", +1), add="+")
                child.bind("<Shift-Button-4>", linux_wheel("x", -1), add="+")
                child.bind("<Shift-Button-5>", linux_wheel("x", +1), add="+")
            register_descendants(child)

    def update_scroll_region(_event=None):
        bounds = canvas.bbox("all")
        if bounds is not None:
            canvas.configure(scrollregion=bounds)
        register_descendants(content)

    def resize_content(event):
        requested = content.winfo_reqwidth()
        canvas.itemconfigure(content_id, width=max(event.width, requested, 1))
        update_scroll_region()

    content.bind("<Configure>", update_scroll_region, add="+")
    canvas.bind("<Configure>", resize_content, add="+")
    canvas.bind("<MouseWheel>", on_vertical, add="+")
    canvas.bind("<Shift-MouseWheel>", on_horizontal, add="+")
    canvas.bind("<Button-4>", linux_wheel("y", -1), add="+")
    canvas.bind("<Button-5>", linux_wheel("y", 1), add="+")
    canvas.bind("<Shift-Button-4>", linux_wheel("x", -1), add="+")
    canvas.bind("<Shift-Button-5>", linux_wheel("x", 1), add="+")
    canvas.bind("<Prior>", lambda event: canvas.yview_scroll(-1, "pages"), add="+")
    canvas.bind("<Next>", lambda event: canvas.yview_scroll(+1, "pages"), add="+")
    canvas.bind("<Home>", lambda event: canvas.yview_moveto(0), add="+")
    canvas.bind("<End>", lambda event: canvas.yview_moveto(1), add="+")
    host._cleanroomx_scroll_canvas = canvas
    host._cleanroomx_scroll_vertical = vertical
    host._cleanroomx_scroll_horizontal = horizontal
    return content
