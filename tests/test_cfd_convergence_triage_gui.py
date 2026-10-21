"""Real Tk smoke for recorded SIMPLE numerical triage; synthetic history only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tkinter as tk

import pytest

from cleanroomx.cfd_multizone_gui import MultizoneCFDWindow
from cleanroomx.cfd_multizone_stability import compare_recorded_iterations
from test_cfd_multizone_stability import _series


@pytest.fixture
def gui():
    try:
        root=tk.Tk()
    except tk.TclError as exc:
        if os.name=="nt" or os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk requires a display: {exc}")
    window=MultizoneCFDWindow(root)
    root.update()
    try:
        yield root,window
    finally:
        if window.winfo_exists():
            window.running=False
            window.close()
        root.destroy()


def test_saved_snapshot_triage_shows_recorded_drift_not_certification(gui,tmp_path,monkeypatch):
    root,window=gui
    assert window.open_convergence_triage() is None
    assert "Analyze genuine saved" in window.history_status.get()
    history=compare_recorded_iterations(_series())
    window.load_iteration_history(history)
    root.update()
    assert "room_speed" in window.history_table["columns"]
    latest_row=window.history_table.item(window.history_table.get_children()[-1],"values")
    assert float(latest_row[-1])==pytest.approx(.04)
    assert window.tabs.select()==str(window.history_tab)
    assert window.tabs.tab(window.tabs.select(),"text")=="Iteration stability"
    dialog=window.open_convergence_triage()
    assert isinstance(dialog,tk.Toplevel)
    root.update()
    report=dialog._cleanroomx_convergence_latest["value"]
    assert report["numerical_screening"]=="solver_not_converged"
    assert report["engineering_release"]=="HOLD"
    assert len(dialog._cleanroomx_convergence_table.get_children())==2
    assert "speed" in dialog._cleanroomx_convergence_table["columns"]
    assert "ENGINEERING HOLD" in dialog._cleanroomx_convergence_status.get()
    # A different operator limit changes only the diagnostic breaches.
    entries=dialog._cleanroomx_convergence_variables
    entries["pressure_drift_limit_pa"].set("10")
    entries["speed_drift_limit_m_s"].set("10")
    entries["transfer_drift_limit_m3_s"].set("1")
    entries["cell_imbalance_limit_m3_s"].set("10")
    assert dialog._cleanroomx_convergence_review()
    assert not dialog._cleanroomx_convergence_latest["value"]["observed_breaches"]
    assert dialog._cleanroomx_convergence_latest["value"]["numerical_screening"]=="solver_not_converged"
    # Fail-closed values cannot be exported as a valid numerical review.
    entries["pressure_drift_limit_pa"].set("nan")
    assert not dialog._cleanroomx_convergence_review()
    assert dialog._cleanroomx_convergence_latest["value"] is None
    assert "rejected" in dialog._cleanroomx_convergence_status.get()
    entries["pressure_drift_limit_pa"].set("10")
    entries["speed_drift_limit_m_s"].set("nan")
    assert not dialog._cleanroomx_convergence_review()
    assert dialog._cleanroomx_convergence_latest["value"] is None
    entries["speed_drift_limit_m_s"].set("10")
    assert dialog._cleanroomx_convergence_review()
    saved=tmp_path/"review.json"
    monkeypatch.setattr(
        "cleanroomx.cfd_multizone_gui.filedialog.asksaveasfilename",
        lambda **kwargs:str(saved),
    )
    assert dialog._cleanroomx_convergence_export()
    data=json.loads(saved.read_text(encoding="utf-8"))
    assert data["schema"]=="cleanroomx.multizone-convergence-triage.v1"
    assert data["closed_door_5pa_demonstrated"] is False
    assert not dialog._cleanroomx_convergence_export()
    assert "export rejected" in dialog._cleanroomx_convergence_status.get()
    dialog.destroy()
