from __future__ import annotations

import os
from pathlib import Path

import pytest

import cleanroomx.gui as gui_module
from cleanroomx.application import (
    ExternalDependencyStaleError,
    analysis_run_freshness,
    require_analysis_run_fresh,
    run_analysis,
)
from cleanroomx.gui import CleanroomXApp


ROOT = Path(__file__).resolve().parents[1]


def _copy_example(tmp_path: Path, name: str) -> None:
    (tmp_path / name).write_bytes((ROOT / "examples" / name).read_bytes())


def _consistency_run(tmp_path: Path):
    _copy_example(tmp_path, "facility_project.json")
    _copy_example(tmp_path, "consistency_hvac_demo.json")
    payload = {
        "verification_project": "facility_project.json",
        "hvac_project": "consistency_hvac_demo.json",
        "room_airflow_abs_tolerance_m3_h": 0.0,
        "require_same_room_set": True,
    }
    return run_analysis("consistency", payload, base_dir=tmp_path)


def test_analysis_run_freshness_accepts_unchanged_external_inputs(tmp_path):
    run = _consistency_run(tmp_path)

    assessment = analysis_run_freshness(run, base_dir=tmp_path)

    assert assessment["fresh"] is True
    assert assessment["status"] == "current"
    assert assessment["external_dependency_count"] == 2
    assert {
        item["status"] for item in assessment["external_dependencies"]
    } == {"current"}
    assert require_analysis_run_fresh(run, base_dir=tmp_path) == assessment


def test_analysis_run_freshness_rejects_content_changed_after_run(tmp_path):
    run = _consistency_run(tmp_path)
    dependency = tmp_path / "consistency_hvac_demo.json"
    dependency.write_text(
        dependency.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    assessment = analysis_run_freshness(run, base_dir=tmp_path)
    changed = {
        item["field"]: item for item in assessment["external_dependencies"]
    }["hvac_project"]

    assert assessment["fresh"] is False
    assert assessment["status"] == "stale"
    assert changed["status"] == "content_changed"
    assert changed["current_content_matches_run"] is False
    assert changed["current_sha256"] != changed["expected_sha256"]
    with pytest.raises(ExternalDependencyStaleError, match="out of date") as raised:
        require_analysis_run_fresh(run, base_dir=tmp_path)
    assert [item["field"] for item in raised.value.changes] == ["hvac_project"]


def test_analysis_run_freshness_rejects_missing_dependency_after_run(tmp_path):
    run = _consistency_run(tmp_path)
    (tmp_path / "facility_project.json").unlink()

    assessment = analysis_run_freshness(run, base_dir=tmp_path)
    missing = {
        item["field"]: item for item in assessment["external_dependencies"]
    }["verification_project"]

    assert assessment["fresh"] is False
    assert missing["status"] == "unavailable_or_unstable"
    assert missing["current_content_matches_run"] is False


def test_analysis_run_freshness_accepts_metadata_only_timestamp_change(tmp_path):
    run = _consistency_run(tmp_path)
    dependency = tmp_path / "facility_project.json"
    before = dependency.stat()
    os.utime(
        dependency,
        ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000),
    )

    assessment = analysis_run_freshness(run, base_dir=tmp_path)
    changed = {
        item["field"]: item for item in assessment["external_dependencies"]
    }["verification_project"]

    assert assessment["fresh"] is True
    assert changed["status"] == "current_content_metadata_changed"
    assert changed["current_content_matches_run"] is True
    assert changed["current_sha256"] == changed["expected_sha256"]


def test_analysis_run_freshness_is_current_for_inline_analysis_without_files():
    payload = {
        "name": "Inline room",
        "dimensions": {"length_m": 5.0, "width_m": 4.0, "height_m": 3.0},
        "supply_airflow_m3_h": 1800.0,
        "required_ach": 10.0,
    }
    run = run_analysis("room_verification", payload)

    assessment = analysis_run_freshness(run)

    assert assessment["fresh"] is True
    assert assessment["external_dependency_count"] == 0
    assert assessment["external_dependencies"] == []


def test_gui_restore_discards_file_backed_run_that_became_stale(tmp_path):
    run = _consistency_run(tmp_path)
    (tmp_path / "facility_project.json").write_text(
        (tmp_path / "facility_project.json").read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    class Status:
        def set(self, value):
            self.value = value

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.project_path = tmp_path / "demo.cleanroomx.json"
    app._recovery_source_path = None
    app._runs_by_analysis = {"consistency-a": run}
    app.last_run = None
    app.last_run_analysis_id = None
    app.status_var = Status()
    app.result_text = object()
    app.report_text = object()
    app.diagnostics_text = object()
    cleared = []
    rendered = []
    app._set_text = lambda widget, value: cleared.append((widget, value))
    app._draw_plot = lambda: cleared.append(("plot", None))
    app._render_run = lambda value, select_results=True: rendered.append(value)

    assert app._restore_run_for("consistency-a") is False
    assert app._runs_by_analysis == {}
    assert app.last_run is None
    assert app.last_run_analysis_id is None
    assert rendered == []
    assert "out of date" in app.status_var.value.lower()


@pytest.mark.parametrize(
    "method_name",
    ["export_result_json", "export_run_bundle_json", "export_report_markdown"],
)
def test_gui_exports_block_stale_file_backed_evidence(
    tmp_path, monkeypatch, method_name
):
    run = _consistency_run(tmp_path)
    dependency = tmp_path / "consistency_hvac_demo.json"
    dependency.write_text(
        dependency.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )

    class Status:
        def set(self, value):
            self.value = value

    app = CleanroomXApp.__new__(CleanroomXApp)
    app.root = object()
    app.project_path = tmp_path / "demo.cleanroomx.json"
    app._recovery_source_path = None
    app._runs_by_analysis = {"consistency-a": run}
    app.last_run = run
    app.last_run_analysis_id = "consistency-a"
    app.status_var = Status()
    app.result_text = object()
    app.report_text = object()
    app.diagnostics_text = object()
    app._set_text = lambda widget, value: None
    app._draw_plot = lambda: None

    chooser_called = []
    warnings = []
    monkeypatch.setattr(
        gui_module.filedialog,
        "asksaveasfilename",
        lambda **kwargs: chooser_called.append(True) or str(tmp_path / "should-not-exist"),
    )
    monkeypatch.setattr(
        gui_module.messagebox,
        "showwarning",
        lambda title, message, parent=None: warnings.append((title, message, parent)),
    )

    getattr(app, method_name)()

    assert chooser_called == []
    assert app._runs_by_analysis == {}
    assert app.last_run is None
    assert app.last_run_analysis_id is None
    assert warnings
    assert warnings[0][0] == "Result out of date"
    assert "run the analysis again" in warnings[0][1].lower()
