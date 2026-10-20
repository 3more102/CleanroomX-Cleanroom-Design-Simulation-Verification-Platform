"""Windows/WSL desktop integration contracts; no solver is faked as evidence."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tkinter as tk

import pytest

from cleanroomx import cfd_multizone_gui as gui


def test_wsl_gui_command_probe_preserves_failure(monkeypatch, tmp_path):
    calls=[]
    def fake_bridge(**kwargs):
        calls.append(kwargs)
        return 0 if kwargs["mode"]=="probe" else 11
    monkeypatch.setattr(gui,"run_wsl_bridge",fake_bridge)
    assert gui.wsl_gui_command(
        repository=tmp_path,distribution="Ubuntu",mode="probe"
    ) == {"status":"wsl_probe_ready"}
    assert calls[0]["repository"]==tmp_path
    assert calls[0]["case_directory"] is None
    with pytest.raises(RuntimeError,match="code 11"):
        gui.wsl_gui_command(
            repository=tmp_path, directory=tmp_path,
            distribution="Ubuntu", mode="run",
        )
    with pytest.raises(ValueError,match="Unsupported"):
        gui.wsl_gui_command(repository=tmp_path,mode="invalid")


def test_wsl_gui_requires_real_matching_run_receipt(monkeypatch,tmp_path):
    case=tmp_path/"solver case"
    case.mkdir()
    (case/"manifest.json").write_text('{"example":true}')
    digest=hashlib.sha256((case/"manifest.json").read_bytes()).hexdigest()
    monkeypatch.setattr(gui,"run_wsl_bridge",lambda **kwargs:0)
    with pytest.raises(RuntimeError,match="without a readable execution receipt"):
        gui.wsl_gui_command(repository=tmp_path,directory=case,mode="run")
    receipt=case/"run-receipt.json"
    for data in (
        {"status":"incomplete","manifest_sha256":digest},
        {"status":"executed_requires_convergence_review","manifest_sha256":"0"*64},
        [1,2,3],
    ):
        receipt.write_text(json.dumps(data))
        with pytest.raises(RuntimeError,match="missing, stale or incomplete"):
            gui.wsl_gui_command(repository=tmp_path,directory=case,mode="run")
    receipt.write_text(json.dumps({
        "status":"executed_requires_convergence_review",
        "manifest_sha256":digest,
    }))
    assert gui.wsl_gui_command(
        repository=tmp_path,directory=case,distribution="Ubuntu",mode="run"
    )=={"status":"wsl_solver_executed_requires_convergence_review"}


@pytest.fixture
def tkinter_window():
    try:
        root=tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY") or os.name=="nt":
            raise
        pytest.skip(f"Real Tk display required: {exc}")
    window=gui.MultizoneCFDWindow(root)
    root.update()
    try:
        yield root,window
    finally:
        if window.winfo_exists():
            window.running=False
            window.close()
        root.destroy()


def test_native_wsl_controls_and_worker_routing(tkinter_window,monkeypatch,tmp_path):
    root,window=tkinter_window
    assert window.wsl_run_button.cget("text")=="Run case in WSL"
    assert window.wsl_probe_button.cget("text")=="Probe WSL"
    assert window.wsl_distribution.get()=="Ubuntu"
    case=tmp_path/"new-case"
    case.mkdir()
    calls=[]
    monkeypatch.setattr(gui,"_windows_wsl_available",lambda:True)
    monkeypatch.setattr(gui,"verify_multizone_inputs",lambda folder:(Path(folder),{}))
    def fake_operation(**kwargs):
        calls.append(kwargs)
        return {"status":(
            "wsl_probe_ready" if kwargs["mode"]=="probe"
            else "wsl_solver_executed_requires_convergence_review"
        )}
    monkeypatch.setattr(gui,"wsl_gui_command",fake_operation)
    def sync_worker(callback):
        window.running=True
        window.events.put(("result",callback()))
    monkeypatch.setattr(window,"_worker",sync_worker)
    window.case_path.set(str(case))
    window.wsl_distribution.set("Ubuntu-Test")
    window.run_wsl_case()
    assert calls[-1]["directory"]==case
    assert calls[-1]["distribution"]=="Ubuntu-Test"
    assert calls[-1]["mode"]=="run"
    window._poll()
    assert not window.running
    assert "wsl solver executed" in window.status.get()
    window.probe_wsl()
    assert calls[-1]["mode"]=="probe"
    assert calls[-1]["distribution"]=="Ubuntu-Test"
    window._poll()
    assert "probe READY" in window.status.get()
    assert not window.running


def test_gui_tails_only_genuine_wsl_logs_without_replaying_prior_bytes(
    tkinter_window,tmp_path,
):
    root,window=tkinter_window
    case=tmp_path/"recorded-case"
    case.mkdir()
    stage=case/"blockMesh.log"
    stage.write_text("Real mesh header\n",encoding="utf-8")
    window._wsl_running_case=case
    window._poll_wsl_logs()
    once=window.log_text.get("1.0","end")
    assert once.count("Real mesh header")==1
    assert "--- WSL: blockMesh (recorded log) ---" in once
    window._poll_wsl_logs()
    assert window.log_text.get("1.0","end").count("Real mesh header")==1
    with stage.open("a",encoding="utf-8") as out:
        out.write("New mesh diagnostic\n")
    (case/"checkMesh.log").write_text("Real checkMesh result\n",encoding="utf-8")
    window._poll_wsl_logs()
    output=window.log_text.get("1.0","end")
    assert output.count("Real mesh header")==1
    assert output.count("New mesh diagnostic")==1
    assert output.count("Real checkMesh result")==1
    window._poll_wsl_logs()
    assert window.log_text.get("1.0","end").count("Real checkMesh result")==1
