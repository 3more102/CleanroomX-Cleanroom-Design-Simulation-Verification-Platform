"""Real Tk ownership tests; unsafe finalizers are observed without calling Tcl."""
from concurrent.futures import ThreadPoolExecutor
import gc
import os
import threading
import tkinter as tk
import weakref

import pytest

from cleanroomx.gui_lifecycle import collect_retired_tk_objects, protect_tk_lifecycle


@pytest.fixture
def root():
    try:
        application = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Real Tk display required: {exc}")
    yield application
    try:
        application.destroy()
    except tk.TclError:
        pass
    collect_retired_tk_objects()


def _observed_variable(root, finalized, rescued):
    class ObservedVariable(tk.StringVar):
        def __del__(self):
            finalized.append(threading.get_ident())
            if threading.current_thread() is not threading.main_thread():
                rescued.append(self)  # Avoid the known Tcl crash in the failing case.
                return
            super().__del__()
    variable = ObservedVariable(master=root, value="retained UI state")
    variable.cycle = variable
    return variable


def test_unprotected_variable_cycle_exposes_background_finalizer_ownership(root):
    finalized, rescued = [], []
    variable = _observed_variable(root, finalized, rescued)
    del variable
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(gc.collect).result(timeout=3)
    assert finalized and finalized[0] != threading.get_ident()
    for variable in rescued:
        tk.Variable.__del__(variable)
        variable.cycle = None
    rescued.clear()


@pytest.mark.parametrize("collect_while_caller_still_owns_window", [False, True])
def test_destroyed_widgets_and_variables_finalize_on_gui_thread(root, collect_while_caller_still_owns_window):
    finalized, rescued = [], []
    protect_tk_lifecycle(root)
    window = tk.Toplevel(root)
    window.variable = _observed_variable(root, finalized, rescued)
    reference = weakref.ref(window.variable)
    window.destroy()
    if collect_while_caller_still_owns_window:
        collect_retired_tk_objects()
        assert reference() is not None
    del window
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(gc.collect).result(timeout=3)
    assert finalized == [] and rescued == []
    collect_retired_tk_objects()
    assert finalized == [threading.get_ident()]
    assert reference() is None


def test_collection_preserves_preexisting_automatic_gc_policy(root):
    protect_tk_lifecycle(root)
    child = tk.Frame(root)
    child.destroy()
    was_enabled = gc.isenabled()
    gc.disable()
    try:
        collect_retired_tk_objects()
        assert not gc.isenabled()
    finally:
        if was_enabled:
            gc.enable()


def test_collection_rejects_background_thread_calls():
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(RuntimeError, match="main GUI thread"):
            pool.submit(collect_retired_tk_objects).result(timeout=3)
