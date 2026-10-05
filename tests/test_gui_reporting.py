from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_reporting import ReportingWorkspace, build_reporting_snapshot


def _snapshot(**overrides):
    values = {
        "project_name": "Project Alpha",
        "project_path": "/tmp/project.cleanroomx.json",
        "project_dirty": False,
        "running": False,
        "analysis_name": "Room verification",
        "analysis_kind": "verification",
        "run_title": "Room verification report",
        "run_status": "complete",
        "run_markdown": "# Verified report\n\nBackend evidence.",
        "run_is_current": True,
        "freshness_error": None,
        "diagnostics": {
            "summary": {
                "status": "warning",
                "issue_count": 3,
                "error_count": 1,
                "warning_count": 2,
                "info_count": 0,
            }
        },
    }
    values.update(overrides)
    return build_reporting_snapshot(**values)


def test_reporting_snapshot_never_promotes_missing_or_stale_results():
    missing = _snapshot(
        project_path=None,
        analysis_name="ACH",
        run_title=None,
        run_status=None,
        run_markdown=None,
        run_is_current=False,
    )
    assert missing["analysis"]["state"] == "not_run"
    assert not missing["analysis"]["export_ready"]
    assert missing["dossier"]["state"] == "save_required"
    assert not missing["dossier"]["export_ready"]
    assert "not shown as zero" in missing["preview"]

    stale = _snapshot(run_is_current=False)
    assert stale["analysis"]["state"] == "stale"
    assert not stale["analysis"]["export_ready"]
    assert "Verified report" not in stale["preview"]

    unverifiable = _snapshot(
        run_is_current=False,
        freshness_error="dependency fingerprint unavailable",
    )
    assert unverifiable["analysis"]["state"] == "freshness_unavailable"
    assert not unverifiable["analysis"]["export_ready"]
    assert "dependency fingerprint unavailable" in unverifiable["analysis"]["detail"]


def test_reporting_snapshot_separates_analysis_and_revision_bound_dossier_readiness():
    ready = _snapshot()
    assert ready["analysis"]["state"] == "ready"
    assert ready["analysis"]["export_ready"]
    assert ready["dossier"]["state"] == "ready"
    assert ready["dossier"]["export_ready"]
    assert ready["diagnostics"]["error_count"] == 1
    assert ready["diagnostics"]["warning_count"] == 2
    assert ready["preview"].startswith("# Verified report")

    dirty = _snapshot(project_dirty=True)
    assert dirty["analysis"]["export_ready"]
    assert dirty["dossier"]["state"] == "unsaved"
    assert not dirty["dossier"]["export_ready"]

    running = _snapshot(running=True)
    assert running["analysis"]["export_ready"]
    assert running["dossier"]["state"] == "running"
    assert not running["dossier"]["export_ready"]


@pytest.fixture
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    window.geometry("1000x700")
    try:
        yield window
    finally:
        window.destroy()


def test_reporting_widget_disables_actions_until_backend_state_is_publishable(root):
    state = {
        "value": _snapshot(
            project_path=None,
            run_title=None,
            run_status=None,
            run_markdown=None,
            run_is_current=False,
        )
    }
    calls: list[str] = []
    widget = ReportingWorkspace(
        root,
        snapshot_getter=lambda: state["value"],
        export_dossier=lambda: calls.append("dossier"),
        export_markdown=lambda: calls.append("markdown"),
        export_html=lambda: calls.append("html"),
        export_result=lambda: calls.append("result"),
    )
    widget.pack(fill="both", expand=True)
    root.update()

    assert str(widget.markdown_button.cget("state")) == "disabled"
    assert str(widget.html_button.cget("state")) == "disabled"
    assert str(widget.result_button.cget("state")) == "disabled"
    assert str(widget.dossier_button.cget("state")) == "disabled"

    state["value"] = _snapshot()
    widget.refresh()
    root.update()

    assert str(widget.markdown_button.cget("state")) == "normal"
    assert str(widget.html_button.cget("state")) == "normal"
    assert str(widget.result_button.cget("state")) == "normal"
    assert str(widget.dossier_button.cget("state")) == "normal"
    assert "Verified report" in widget.preview_text.get("1.0", "end")

    widget.markdown_button.invoke()
    assert calls == ["markdown"]


@pytest.fixture
def app(tmp_path):
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        if os.environ.get("DISPLAY"):
            raise
        pytest.skip(f"Tk display unavailable: {exc}")
    callback_errors = []
    root.report_callback_exception = lambda *args: callback_errors.append(args)
    application = CleanroomXApp(
        root,
        autosave_interval_seconds=0,
        ui_state_path=tmp_path / "gui-layout.json",
    )
    application.load_project_path(bundled_demo_project_path())
    root.update()
    try:
        yield application
        assert callback_errors == []
    finally:
        root.destroy()


def test_reporting_profile_is_first_class_central_workspace_without_project_mutation(app):
    before = copy.deepcopy(app.project.to_dict())

    app.activate_workspace_profile("reporting")
    app.root.update()

    assert app.notebook.select() == str(app.reporting_workspace)
    assert app.output_notebook.select() == str(app.report_text.master)
    assert app.reporting_workspace.last_snapshot["project"]["name"] == app.project.name
    assert app.project.to_dict() == before


def test_completed_current_run_populates_reporting_preview_and_export_readiness(app):
    run = app.smoke_run_active()
    app.activate_workspace_profile("reporting")
    app.root.update()

    snapshot = app.reporting_workspace.last_snapshot
    assert snapshot["analysis"]["state"] == "ready"
    assert snapshot["analysis"]["export_ready"]
    assert snapshot["preview"].strip() == run.markdown.strip()
    assert str(app.reporting_workspace.markdown_button.cget("state")) == "normal"
    assert str(app.reporting_workspace.html_button.cget("state")) == "normal"
    assert str(app.reporting_workspace.result_button.cget("state")) == "normal"
