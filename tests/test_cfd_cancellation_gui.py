"""Real Tk routing checks; controlled workers provide no CFD evidence."""
import os
import threading
import time
import tkinter as tk

import pytest

from cleanroomx import cfd_multizone_gui as gui


@pytest.fixture
def window():
    try:
        root=tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Real Tk display required: {exc}")
    errors=[]
    root.report_callback_exception=lambda *args:errors.append(args)
    view=gui.MultizoneCFDWindow(root)
    yield root,view,errors
    try:
        root.destroy()
    except tk.TclError:
        pass  # One regression deliberately closes the entire parent app.
    assert errors==[]


def _drain(root,view):
    deadline=time.monotonic()+4
    while view.running and time.monotonic()<deadline:
        root.update()
        time.sleep(.01)
    assert not view.running


def test_cancel_button_remains_responsive_and_never_opens_partial_fields(window,monkeypatch,tmp_path):
    root,view,errors=window
    entered=threading.Event()
    def run(directory,*,on_progress,cancel_event):
        entered.set()
        assert cancel_event.wait(3)
        return {"status":"cancelled"}
    monkeypatch.setattr(gui,"verify_multizone_inputs",lambda path:(tmp_path,{}))
    monkeypatch.setattr(gui,"run_multizone_open_door_case",run)
    monkeypatch.setattr(gui.messagebox,"showerror",lambda *a,**kw:pytest.fail("Unexpected error dialog"))
    view.run_case()
    assert entered.wait(1)
    assert view.running
    assert str(view.cancel_native_button["state"])=="normal"
    view.close()
    assert view.winfo_exists()
    assert "Cancel native run" in view.status.get()
    view.cancel_native_button.invoke()
    _drain(root,view)
    assert "cancelled" in view.status.get()
    assert "cannot be imported" in view.status.get()
    assert view.report is None
    assert str(view.cancel_native_button["state"])=="disabled"


def test_destroying_parent_requests_native_cleanup_without_worker_tk_access(window,monkeypatch,tmp_path):
    root,view,errors=window
    cleaned=threading.Event()
    def run(directory,*,on_progress,cancel_event):
        assert cancel_event.wait(3)
        cleaned.set()
        return {"status":"cancelled"}
    monkeypatch.setattr(gui,"verify_multizone_inputs",lambda path:(tmp_path,{}))
    monkeypatch.setattr(gui,"run_multizone_open_door_case",run)
    view.run_case()
    root.destroy()
    assert cleaned.wait(2)


def test_wsl_and_import_workers_do_not_offer_native_cancellation(window):
    root,view,errors=window
    done=threading.Event()
    view._worker(lambda:done.wait(3) and {"status":"wsl_probe_ready"})
    try:
        assert str(view.cancel_native_button["state"])=="disabled"
        view.cancel_native_run()
        assert view._native_cancel_event is None
    finally:
        done.set()
        _drain(root,view)
