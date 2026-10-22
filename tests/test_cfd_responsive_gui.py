"""Real-Tk desktop integration tests for responsive multiroom CFD controls."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
import pytest

from cleanroomx import cfd_multizone_gui as gui
from cleanroomx.gui_scrollable import create_scrollable_content


@pytest.fixture
def desktop():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY") or os.name == "nt":
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    try:
        yield root
    finally:
        root.destroy()


def test_windows_wsl_controls_are_collapsed_and_restored(desktop, monkeypatch):
    monkeypatch.setattr(gui, "_windows_wsl_available", lambda: True)
    dialog = gui.MultizoneCFDWindow(desktop)
    try:
        dialog.update()
        assert dialog.wsl_probe_button.winfo_exists()
        assert dialog.wsl_run_button.winfo_exists()
        assert dialog.wsl_settings_button.winfo_manager() == "pack"
        assert all(row.winfo_manager() == "" for row in dialog._wsl_rows)
        dialog.toggle_wsl_settings()
        dialog.update()
        assert all(row.winfo_manager() == "pack" for row in dialog._wsl_rows)
        assert dialog.wsl_settings_button.cget("text") == "Hide WSL settings"
        dialog.toggle_wsl_settings()
        dialog.update()
        assert all(row.winfo_manager() == "" for row in dialog._wsl_rows)
    finally:
        dialog.close()


def test_linux_hides_wsl_without_hiding_native_solver_actions(desktop, monkeypatch):
    monkeypatch.setattr(gui, "_windows_wsl_available", lambda: False)
    dialog = gui.MultizoneCFDWindow(desktop)
    try:
        dialog.update()
        assert dialog.wsl_settings_button.winfo_manager() == ""
        assert all(row.winfo_manager() == "" for row in dialog._wsl_rows)
        assert dialog.run_button.winfo_manager() == "pack"
        assert dialog.import_button.winfo_manager() == "pack"
    finally:
        dialog.close()


def test_tab_navigation_follows_notebook(desktop, monkeypatch):
    monkeypatch.setattr(gui, "_windows_wsl_available", lambda: False)
    dialog = gui.MultizoneCFDWindow(desktop)
    try:
        dialog.update()
        dialog.tabs.select(3)
        dialog.update()
        assert dialog.tab_picker.current() == 3
        dialog.tab_picker.current(0)
        dialog.tab_picker.event_generate("<<ComboboxSelected>>")
        dialog.update()
        assert dialog.tabs.index("current") == 0
    finally:
        dialog.close()


def test_plain_chart_scrolls_containing_tab(desktop):
    desktop.deiconify()
    desktop.geometry("510x280")
    host = ttk.Frame(desktop)
    host.pack(fill="both", expand=True)
    page = create_scrollable_content(host)
    chart = tk.Canvas(page, width=1100, height=180)
    chart.pack()
    for i in range(100):
        ttk.Label(page, text=f"Observed numerical result {i}").pack()
    desktop.update()
    parent = host._cleanroomx_scroll_canvas
    before = parent.yview()[0]
    chart.event_generate("<MouseWheel>", delta=-120)
    desktop.update()
    assert parent.yview()[0] > before
