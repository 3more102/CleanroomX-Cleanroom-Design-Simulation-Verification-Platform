from __future__ import annotations

import copy
import os
import tkinter as tk

import pytest

from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path
from cleanroomx.gui_search import SearchEntry
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


def test_global_search_evidence_focuses_exact_persisted_proofgraph_node(
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

    viewer = app.proofgraph_viewer
    viewer.filter_var.set("Failures")
    viewer.search_var.set("does-not-exist")
    viewer._refresh()
    assert "evidence:EVID-GUI-PRESSURE" not in viewer._nodes_by_key

    entry = SearchEntry(
        key="proof:GRAPH-GUI-PRESSURE:evidence:EVID-GUI-PRESSURE",
        category="Evidence",
        label="pressure_pa",
        target_type="evidence",
        target_id="EVID-GUI-PRESSURE",
        payload={
            "id": "EVID-GUI-PRESSURE",
            "type": "evidence",
            "_proofgraph_id": "GRAPH-GUI-PRESSURE",
            "_proofgraph_key": "evidence:EVID-GUI-PRESSURE",
        },
    )
    app._navigate_engineering_search_result(entry)
    app.root.update()

    assert app.notebook.select() == str(viewer)
    assert viewer.filter_var.get() == "All"
    assert viewer.search_var.get() == ""
    assert viewer.selected_node()["key"] == "evidence:EVID-GUI-PRESSURE"
    assert "focused on search result" in app.status_var.get()


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
