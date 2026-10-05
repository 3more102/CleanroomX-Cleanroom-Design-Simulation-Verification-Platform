from __future__ import annotations

import os
import tkinter as tk
from types import SimpleNamespace

import pytest

from cleanroomx.gui_reporting import ReportingWorkspace
from cleanroomx.gui_theme import theme_palette


@pytest.fixture
def workspace():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    root.withdraw()
    widget = ReportingWorkspace(
        root,
        export_dossier=lambda: None,
        export_result_json=lambda: None,
        export_run_bundle=lambda: None,
        export_markdown=lambda: None,
        export_html=lambda: None,
    )
    widget.pack(fill="both", expand=True)
    root.update()
    try:
        yield widget
    finally:
        root.destroy()


def test_reporting_readiness_requires_saved_clean_project_and_current_run(workspace):
    workspace.set_context(
        project_name="Demo",
        project_path=None,
        unsaved_changes=False,
        run=None,
    )
    assert str(workspace.dossier_button.cget("state")) == "disabled"
    assert str(workspace.markdown_button.cget("state")) == "disabled"
    assert "save project first" in workspace.dossier_var.get().lower()

    workspace.set_context(
        project_name="Demo",
        project_path="/tmp/demo.cleanroomx.json",
        unsaved_changes=True,
        run=None,
    )
    assert str(workspace.dossier_button.cget("state")) == "disabled"
    assert "save changes first" in workspace.dossier_var.get().lower()

    run = SimpleNamespace(
        title="ACH Verification",
        status="pass",
        markdown="# ACH Verification\n\nVerified backend report.",
    )
    workspace.set_context(
        project_name="Demo",
        project_path="/tmp/demo.cleanroomx.json",
        unsaved_changes=False,
        run=run,
    )
    assert str(workspace.dossier_button.cget("state")) == "normal"
    assert str(workspace.markdown_button.cget("state")) == "normal"
    assert str(workspace.html_button.cget("state")) == "normal"
    assert str(workspace.result_button.cget("state")) == "normal"
    assert str(workspace.bundle_button.cget("state")) == "normal"
    assert "ACH Verification" in workspace.run_var.get()
    assert "Verified backend report." in workspace.preview.get("1.0", "end-1c")


def test_reporting_theme_applies_to_preview(workspace):
    palette = theme_palette("dark")
    workspace.apply_theme(palette)
    assert workspace.preview.cget("background") == palette["field"]
    assert workspace.preview.cget("foreground") == palette["field_text"]
