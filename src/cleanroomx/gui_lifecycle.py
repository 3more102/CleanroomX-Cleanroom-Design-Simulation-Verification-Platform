"""Keep destroyed Tk object cycles out of background-thread garbage collection.

Tk variables can call Tcl from their finalizer. Python can otherwise collect
an unreachable GUI cycle in a numerical worker (CPython issue 39093). Retain
destroyed widgets until a full collection on the GUI thread, then retain any
survivors still referenced by callers. Automatic GC is paused only during that
short handoff, never for the duration of a simulation.
"""
from __future__ import annotations

import atexit
import gc
import threading
import tkinter as tk
import weakref

_retired: dict[int, tk.Misc] = {}


def collect_retired_tk_objects() -> None:
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Tk object collection must run on the main GUI thread")
    if not _retired:
        return
    enabled = gc.isenabled()
    gc.disable()
    references = [weakref.ref(widget) for widget in _retired.values()]
    try:
        _retired.clear()
        gc.collect(2)
    finally:
        # A caller may still own a destroyed window. Keep protecting it when
        # that caller later releases its last reference during another task.
        for reference in references:
            widget = reference()
            if widget is not None:
                _retired[id(widget)] = widget
        if enabled:
            gc.enable()


def protect_tk_lifecycle(widget: tk.Misc) -> None:
    """Install one destruction/collection boundary per Tcl interpreter."""
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Tk lifecycle protection must be installed on the main GUI thread")
    root = widget._root()
    if getattr(root, "_cleanroomx_lifecycle_protected", False):
        return
    collect_retired_tk_objects()
    root._cleanroomx_lifecycle_protected = True
    state = {"closed": False, "timer": None}

    def destroyed(event):
        target = event.widget
        if isinstance(target, tk.Misc):
            _retired[id(target)] = target
        if target is root:
            state["closed"] = True
            if state["timer"] is not None:
                root.after_cancel(state["timer"])
                state["timer"] = None

    def drain():
        state["timer"] = None
        collect_retired_tk_objects()
        if not state["closed"]:
            state["timer"] = root.after(500, drain)

    root.bind_all("<Destroy>", destroyed, add="+")
    state["timer"] = root.after(500, drain)


def _shutdown_collection() -> None:
    if threading.current_thread() is threading.main_thread():
        collect_retired_tk_objects()


atexit.register(_shutdown_collection)
