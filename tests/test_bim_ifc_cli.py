import copy
import json

from cleanroomx import bim_ifc_cli
from cleanroomx.bim_ifc import (
    IFC_LINK_METADATA_KEY,
    layout_from_ifc_semantics,
    normalize_ifc_semantic_records,
)
from cleanroomx.project import (
    load_project_document,
    new_project,
    save_project_document,
)


def _records():
    return [
        {
            "global_id": "SPACE-001",
            "ifc_class": "IfcSpace",
            "name": "ISO 7 Process",
            "x_m": 1.0,
            "y_m": 2.0,
            "z_m": 0.0,
            "length_m": 6.0,
            "width_m": 5.0,
            "height_m": 3.0,
        },
        {
            "global_id": "AT-001",
            "ifc_class": "IfcAirTerminal",
            "name": "Supply 01",
            "room_global_id": "SPACE-001",
            "predefined_type": "SUPPLYAIR",
            "x_m": 2.0,
            "y_m": 3.0,
            "z_m": 2.8,
        },
    ]


def _provenance(name="facility.ifc", digest="a" * 64):
    return {"source_name": name, "source_sha256": digest}


def _install_extractor(monkeypatch, records, *, name="facility.ifc", digest="a" * 64):
    semantics = normalize_ifc_semantic_records(records)
    monkeypatch.setattr(
        bim_ifc_cli,
        "extract_ifc_semantics",
        lambda _path: (copy.deepcopy(semantics), _provenance(name, digest)),
    )
    return semantics


def test_ifc_cli_initial_import_persists_identity_and_revision_evidence(
    tmp_path, monkeypatch, capsys
):
    project_path = tmp_path / "project.cleanroomx.json"
    ifc_path = tmp_path / "facility.ifc"
    ifc_path.write_text("placeholder", encoding="utf-8")
    save_project_document(project_path, new_project("IFC CLI"))
    semantics = _install_extractor(monkeypatch, _records())

    assert bim_ifc_cli.main(["import", str(project_path), str(ifc_path)]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["schema"] == "cleanroomx.ifc-cli-result"
    assert output["action"] == "import"
    assert output["semantic_sha256"] == semantics["semantic_sha256"]
    assert output["room_count"] == 1
    assert output["device_count"] == 1
    assert output["project_revision_before"]["sha256"]
    assert output["project_revision_after"]["sha256"]
    assert (
        output["project_revision_before"]["sha256"]
        != output["project_revision_after"]["sha256"]
    )

    reopened = load_project_document(project_path)
    assert reopened.metadata[IFC_LINK_METADATA_KEY]["schema_version"] == 2
    assert reopened.metadata[IFC_LINK_METADATA_KEY]["bindings"][0]["global_id"]


def test_ifc_cli_refuses_to_replace_unlinked_spatial_layout_without_opt_in(
    tmp_path, monkeypatch, capsys
):
    project_path = tmp_path / "project.cleanroomx.json"
    ifc_path = tmp_path / "facility.ifc"
    ifc_path.write_text("placeholder", encoding="utf-8")
    semantics = _install_extractor(monkeypatch, _records())

    project = new_project("Existing layout")
    project.metadata["spatial_layout"] = layout_from_ifc_semantics(semantics)
    save_project_document(project_path, project)
    before = project_path.read_bytes()

    assert bim_ifc_cli.main(["import", str(project_path), str(ifc_path)]) == 2
    error = capsys.readouterr().err
    assert "--replace-existing-layout" in error
    assert project_path.read_bytes() == before

    assert (
        bim_ifc_cli.main(
            [
                "import",
                str(project_path),
                str(ifc_path),
                "--replace-existing-layout",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert IFC_LINK_METADATA_KEY in load_project_document(project_path).metadata


def test_ifc_cli_plan_is_read_only_and_returns_one_for_conflict(
    tmp_path, monkeypatch, capsys
):
    project_path = tmp_path / "project.cleanroomx.json"
    ifc_path = tmp_path / "facility.ifc"
    ifc_path.write_text("placeholder", encoding="utf-8")
    save_project_document(project_path, new_project("IFC CLI"))

    _install_extractor(monkeypatch, _records(), digest="a" * 64)
    assert bim_ifc_cli.main(["import", str(project_path), str(ifc_path)]) == 0
    capsys.readouterr()

    locally_edited = load_project_document(project_path)
    locally_edited.metadata["spatial_layout"]["rooms"][0]["length_m"] = 6.5
    save_project_document(project_path, locally_edited)
    before = project_path.read_bytes()

    revised = _records()
    revised[0]["length_m"] = 7.0
    _install_extractor(monkeypatch, revised, digest="b" * 64)

    assert bim_ifc_cli.main(["plan", str(project_path), str(ifc_path)]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["action"] == "plan"
    assert output["plan"]["can_apply"] is False
    assert output["plan"]["conflict_count"] == 1
    assert project_path.read_bytes() == before


def test_ifc_cli_reimport_applies_source_change_without_identity_churn(
    tmp_path, monkeypatch, capsys
):
    project_path = tmp_path / "project.cleanroomx.json"
    ifc_path = tmp_path / "facility.ifc"
    ifc_path.write_text("placeholder", encoding="utf-8")
    save_project_document(project_path, new_project("IFC CLI"))

    _install_extractor(monkeypatch, _records(), digest="a" * 64)
    assert bim_ifc_cli.main(["import", str(project_path), str(ifc_path)]) == 0
    capsys.readouterr()
    original = load_project_document(project_path)
    room_id = original.metadata["spatial_layout"]["rooms"][0]["id"]

    revised = _records()
    revised[0]["name"] = "Renamed Process"
    revised[0]["length_m"] = 7.0
    _install_extractor(monkeypatch, revised, digest="b" * 64)

    assert bim_ifc_cli.main(["reimport", str(project_path), str(ifc_path)]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["action"] == "reimport"
    assert output["plan"]["can_apply"] is True
    assert output["plan"]["summary"]["update"] >= 1

    reopened = load_project_document(project_path)
    room = reopened.metadata["spatial_layout"]["rooms"][0]
    assert room["id"] == room_id
    assert room["name"] == "Renamed Process"
    assert room["length_m"] == 7.0


def test_ifc_cli_refuses_initial_import_when_identity_link_already_exists(
    tmp_path, monkeypatch, capsys
):
    project_path = tmp_path / "project.cleanroomx.json"
    ifc_path = tmp_path / "facility.ifc"
    ifc_path.write_text("placeholder", encoding="utf-8")
    save_project_document(project_path, new_project("IFC CLI"))

    _install_extractor(monkeypatch, _records())
    assert bim_ifc_cli.main(["import", str(project_path), str(ifc_path)]) == 0
    capsys.readouterr()
    before = project_path.read_bytes()

    assert (
        bim_ifc_cli.main(
            [
                "import",
                str(project_path),
                str(ifc_path),
                "--replace-existing-layout",
            ]
        )
        == 2
    )
    assert "use 'cleanroomx-ifc plan'" in capsys.readouterr().err
    assert project_path.read_bytes() == before
