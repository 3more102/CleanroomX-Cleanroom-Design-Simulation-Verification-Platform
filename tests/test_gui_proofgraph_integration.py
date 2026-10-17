from __future__ import annotations

import copy
import os
import tkinter as tk
from types import SimpleNamespace

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_theme import theme_palette
from cleanroomx.proofgraph_models import (
    CalculationEvidence,
    ComplianceCheck,
    ComplianceFinding,
    ComplianceVerdict,
    EvidenceSource,
    ProofGraph,
    ProvenanceRecord,
    Requirement,
    RequirementSet,
    VerificationRun,
)
from cleanroomx.spatial import _Hit


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


def _room_graph(room_id: str) -> dict:
    requirement = Requirement(
        id="REQ-GUI-PRESSURE",
        title="Room pressure",
        source="GUI regression",
        scope=(room_id,),
        criteria={"minimum": 10.0, "unit": "Pa"},
    )
    requirement_set = RequirementSet(
        id="REQSET-GUI",
        version="1",
        title="GUI requirements",
        source="GUI regression",
        requirements=(requirement,),
    )
    source = EvidenceSource(
        id="SRC-GUI-IFC",
        kind="ifc",
        reference="facility.ifc",
    )
    evidence = CalculationEvidence(
        id="EVID-GUI-PRESSURE",
        property_name="pressure_pa",
        value=12.0,
        unit="Pa",
        source_id=source.id,
        subject_ref=room_id,
        provenance=(
            ProvenanceRecord(
                id="PROV-GUI-PRESSURE",
                source_id=source.id,
                origin="GUI regression evidence",
                ifc_global_id="IFC-GUI-ROOM",
                cleanroomx_entity_id=room_id,
                originating_calculation="pressure_solver",
                method="pressure cascade",
            ),
        ),
    )
    check = ComplianceCheck(
        id="CHECK-GUI-PRESSURE",
        requirement_id=requirement.id,
        evidence_ids=(evidence.id,),
        required_evidence_kinds=("calculation",),
    )
    finding = ComplianceFinding(
        id="FIND-GUI-PRESSURE",
        check_id=check.id,
        requirement_id=requirement.id,
        status="pass",
        reason="Pressure meets configured minimum.",
        evidence_ids=(evidence.id,),
        evidence_present=True,
        expected=10.0,
        actual=12.0,
        unit="Pa",
        delta=2.0,
    )
    verdict = ComplianceVerdict(
        id="VERDICT-GUI-PRESSURE",
        requirement_id=requirement.id,
        status="pass",
        finding_ids=(finding.id,),
        reason="Canonical GUI regression verdict.",
    )
    run = VerificationRun(
        id="RUN-GUI-PRESSURE",
        requirement_set_id=requirement_set.id,
        check_ids=(check.id,),
        verdict_ids=(verdict.id,),
    )
    return ProofGraph(
        id="GRAPH-GUI-PRESSURE",
        requirement_set=requirement_set,
        evidence_sources=(source,),
        evidence=(evidence,),
        checks=(check,),
        findings=(finding,),
        verdicts=(verdict,),
        verification_runs=(run,),
    ).to_dict()


def test_persisted_proofgraph_loads_from_history_and_opens_from_navigator(
    app,
    monkeypatch,
):
    room = app.spatial_workspace.layout["rooms"][0]
    document = _room_graph(room["id"])
    monkeypatch.setattr(
        "cleanroomx.gui.verification_run_history_records",
        lambda _metadata: [{"proofgraphs": [document]}],
    )

    app._refresh_engineering_panels()
    app.root.update()

    assert len(app.proofgraph_viewer._documents) == 1
    assert (
        app.proofgraph_viewer._documents[0]["graph_sha256"]
        == document["graph_sha256"]
    )

    assert app.analysis_tree.exists("nav-proofgraph")
    app.analysis_tree.selection_set("nav-proofgraph")
    app.analysis_tree.focus("nav-proofgraph")
    app.analysis_tree.event_generate("<<TreeviewSelect>>")
    app.root.update()

    assert app.notebook.select() == str(app.proofgraph_viewer)


def test_proofgraph_model_object_navigation_syncs_viewport_and_project_browser(app):
    workspace = app.spatial_workspace
    room = workspace.layout["rooms"][0]
    geometry_before = {
        "rooms": copy.deepcopy(workspace.layout["rooms"]),
        "devices": copy.deepcopy(workspace.layout["devices"]),
    }
    document = _room_graph(room["id"])

    app.proofgraph_viewer.set_documents([document])
    model_key = f"model_object:{room['id']}"
    assert model_key in app.proofgraph_viewer._nodes_by_key

    app.proofgraph_viewer._select_key(model_key)
    app.proofgraph_viewer._navigate_selected()
    app.root.update()

    assert workspace.selected == _Hit("room", room["id"])
    assert app.analysis_tree.selection() == (f"room:{room['id']}",)
    assert app.notebook.select() == str(workspace)
    assert workspace.layout["rooms"] == geometry_before["rooms"]
    assert workspace.layout["devices"] == geometry_before["devices"]


def test_tampered_persisted_proofgraph_is_not_rendered(app, monkeypatch):
    room = app.spatial_workspace.layout["rooms"][0]
    document = _room_graph(room["id"])
    document["evidence"][0]["value"] = 99.0
    monkeypatch.setattr(
        "cleanroomx.gui.verification_run_history_records",
        lambda _metadata: [{"proofgraphs": [document]}],
    )

    app._refresh_engineering_panels()
    app.root.update()

    assert app.proofgraph_viewer._documents == []
    assert "unavailable" in app.evidence_text.get("1.0", "end").casefold()


def test_proofgraph_search_and_evidence_readiness_update_live(app):
    room = app.spatial_workspace.layout["rooms"][0]
    document = _room_graph(room["id"])

    app.proofgraph_viewer.set_documents([document])
    app.root.update()

    assert "Evidence: 1/1 checks linked" in app.proofgraph_viewer.readiness_var.get()
    assert "unresolved 0" in app.proofgraph_viewer.readiness_var.get()

    app.proofgraph_viewer.search_var.set("pressure_solver")
    app.root.update()

    keys = set(app.proofgraph_viewer._nodes_by_key)
    assert "calculation:pressure_solver" in keys
    assert "evidence:EVID-GUI-PRESSURE" in keys
    assert "verdict:VERDICT-GUI-PRESSURE" not in keys
    assert app.proofgraph_viewer.summary_var.get().startswith("View: 2/")

    app.proofgraph_viewer._clear_search_and_filter()
    app.root.update()
    assert app.proofgraph_viewer.search_var.get() == ""
    assert app.proofgraph_viewer.filter_var.get() == "All"


def test_proofgraph_viewport_controls_fit_zoom_and_reset(app):
    room = app.spatial_workspace.layout["rooms"][0]
    viewer = app.proofgraph_viewer
    viewer.set_documents([_room_graph(room["id"])])
    app.root.update()

    assert 0.2 <= viewer._zoom <= 1.0
    assert viewer.zoom_var.get() == f"{round(viewer._zoom * 100)}%"

    fitted_zoom = viewer._zoom
    viewer.zoom_in_button.invoke()
    app.root.update()
    assert viewer._zoom > fitted_zoom

    wheel_zoom = viewer._zoom
    viewer._on_zoom_wheel(SimpleNamespace(x=120, y=80, delta=120))
    assert viewer._zoom > wheel_zoom

    viewer.reset_zoom_button.invoke()
    app.root.update()
    assert viewer._zoom == 1.0
    assert viewer.zoom_var.get() == "100%"

    viewer.fit_button.invoke()
    app.root.update()
    assert viewer._zoom <= 1.0

    viewer.reset_zoom_button.invoke()
    viewer.canvas.xview_moveto(0)
    viewer._pan_start(SimpleNamespace(x=200, y=100))
    viewer._pan_drag(SimpleNamespace(x=100, y=100))
    app.root.update()
    assert viewer.canvas.xview()[0] > 0


def test_proofgraph_native_surfaces_follow_light_and_dark_themes(app):
    room = app.spatial_workspace.layout["rooms"][0]
    viewer = app.proofgraph_viewer
    viewer.set_documents([_room_graph(room["id"])])
    app.root.update()

    node = viewer._nodes_by_key["requirement:REQ-GUI-PRESSURE"]
    light_fill = viewer._node_fill(node)
    assert viewer.canvas.cget("background") == theme_palette("light")["canvas_2d"]

    app.set_theme("dark", persist=False)
    app.root.update()

    dark = theme_palette("dark")
    assert viewer.canvas.cget("background") == dark["canvas_2d"]
    assert viewer.canvas.cget("highlightbackground") == dark["border"]
    assert viewer.detail.cget("background") == dark["field"]
    assert viewer.detail.cget("foreground") == dark["field_text"]
    assert viewer._node_fill(node) != light_fill

    app.set_theme("light", persist=False)
    app.root.update()
    assert viewer.canvas.cget("background") == theme_palette("light")["canvas_2d"]
