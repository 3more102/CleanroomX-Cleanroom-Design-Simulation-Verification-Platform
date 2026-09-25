from __future__ import annotations

import json

import pytest

import cleanroomx.project as project_module
from cleanroomx.project import (
    AnalysisDocument,
    PROJECT_INTEGRITY_ALGORITHM,
    PROJECT_INTEGRITY_CANONICALIZATION,
    PROJECT_INTEGRITY_SCOPE,
    PROJECT_SCHEMA,
    PROJECT_SCHEMA_VERSION,
    ProjectDocument,
    ProjectFormatError,
    atomic_write_text,
    load_project_document,
    project_file_dict,
    project_from_dict,
    project_payload_sha256,
    save_project_document,
)


def test_project_document_round_trip(tmp_path):
    project = ProjectDocument(
        name="GUI Demo",
        description="round trip",
        analyses=[AnalysisDocument(
            id="hvac-1", name="HVAC", kind="hvac",
            input={"name": "Demo", "rooms": []},
        )],
        active_analysis_id="hvac-1",
        metadata={"owner": "test"},
    )
    path = save_project_document(tmp_path / "demo.cleanroomx.json", project)
    loaded = load_project_document(path)
    assert loaded == project
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["schema"] == PROJECT_SCHEMA
    assert raw["schema_version"] == PROJECT_SCHEMA_VERSION


def test_atomic_write_text_replaces_content_without_leaving_temp_file(tmp_path):
    target = tmp_path / "export.json"
    target.write_text("old", encoding="utf-8")

    atomic_write_text(target, "new\n")

    assert target.read_text(encoding="utf-8") == "new\n"
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_atomic_write_text_cleans_temp_file_when_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "export.json"

    def fail_replace(self, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(type(target), "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        atomic_write_text(target, "payload\n")

    assert not target.exists()
    assert list(tmp_path.glob(f".{target.name}.*.tmp")) == []


def test_project_loader_migrates_legacy_single_analysis_shape():
    project = project_from_dict({
        "name": "Legacy", "analysis_type": "fan_operating_point",
        "input": {"study": "legacy"},
    })
    assert project.name == "Legacy"
    assert len(project.analyses) == 1
    assert project.analyses[0].kind == "fan_operating_point"
    assert project.active_analysis_id == "analysis-1"


def test_project_loader_migrates_explicit_v0_shape():
    project = project_from_dict({
        "schema": PROJECT_SCHEMA, "schema_version": 0, "name": "Legacy v0",
        "analysis": {
            "id": "a1", "name": "Room", "kind": "room_verification", "input": {},
        },
    })
    assert project.name == "Legacy v0"
    assert project.active_analysis_id == "a1"


def test_project_loader_rejects_future_schema():
    with pytest.raises(ProjectFormatError, match="future"):
        project_from_dict({
            "schema": PROJECT_SCHEMA,
            "schema_version": PROJECT_SCHEMA_VERSION + 1,
            "project": {"name": "Future"}, "analyses": [],
        })


def test_project_loader_rejects_duplicate_analysis_ids():
    with pytest.raises(ProjectFormatError, match="unique"):
        project_from_dict({
            "schema": PROJECT_SCHEMA, "schema_version": PROJECT_SCHEMA_VERSION,
            "project": {"name": "Duplicate"},
            "analyses": [
                {"id": "a", "name": "A", "kind": "hvac", "input": {}},
                {"id": "a", "name": "B", "kind": "hvac", "input": {}},
            ],
            "active_analysis_id": "a",
        })


def test_project_loader_rejects_non_finite_json(tmp_path):
    path = tmp_path / "nonfinite.cleanroomx.json"
    path.write_text(
        '{"schema":"cleanroomx.project","schema_version":1,'
        '"project":{"name":"Bad"},"analyses":['
        '{"id":"a","name":"A","kind":"room_verification","input":{"value":NaN}}'
        '],"active_analysis_id":"a"}',
        encoding="utf-8",
    )
    with pytest.raises(ProjectFormatError, match="non-finite"):
        load_project_document(path)


def test_project_loader_reports_invalid_json(tmp_path):
    path = tmp_path / "bad.cleanroomx.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ProjectFormatError, match="invalid JSON"):
        load_project_document(path)


def test_project_save_embeds_canonical_integrity_record(tmp_path):
    project = ProjectDocument(
        name="Integrity",
        analyses=[
            AnalysisDocument(
                id="room-1",
                name="Room",
                kind="room_verification",
                input={"value": 1.25},
            )
        ],
        active_analysis_id="room-1",
    )

    path = save_project_document(tmp_path / "integrity.cleanroomx.json", project)
    raw = json.loads(path.read_text(encoding="utf-8"))

    assert raw["integrity"] == {
        "algorithm": PROJECT_INTEGRITY_ALGORITHM,
        "canonicalization": PROJECT_INTEGRITY_CANONICALIZATION,
        "scope": PROJECT_INTEGRITY_SCOPE,
        "sha256": project_payload_sha256(raw),
    }


def test_project_loader_rejects_integrity_mismatch_after_content_change(tmp_path):
    path = save_project_document(
        tmp_path / "tampered.cleanroomx.json",
        ProjectDocument(name="Before"),
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["project"]["name"] = "After"
    path.write_text(json.dumps(raw, indent=4) + "\n", encoding="utf-8")

    with pytest.raises(ProjectFormatError, match="SHA-256 mismatch"):
        load_project_document(path)


def test_project_integrity_ignores_json_whitespace_and_key_order(tmp_path):
    path = save_project_document(
        tmp_path / "reformatted.cleanroomx.json",
        ProjectDocument(name="Formatting", metadata={"z": 1, "a": 2}),
    )
    raw = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(
        json.dumps(raw, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    loaded = load_project_document(path)

    assert loaded.name == "Formatting"
    assert loaded.metadata == {"z": 1, "a": 2}


def test_schema_v1_without_integrity_remains_backward_compatible():
    project = project_from_dict({
        "schema": PROJECT_SCHEMA,
        "schema_version": PROJECT_SCHEMA_VERSION,
        "application_version": "0.100.0",
        "project": {
            "name": "Pre-integrity project",
            "description": "",
            "metadata": {},
        },
        "analyses": [],
        "active_analysis_id": None,
    })

    assert project.name == "Pre-integrity project"


def test_project_loader_rejects_unknown_integrity_contract():
    payload = project_file_dict(ProjectDocument(name="Integrity contract"))
    payload["integrity"]["canonicalization"] = "unknown-v999"

    with pytest.raises(ProjectFormatError, match="canonicalization"):
        project_from_dict(payload)


def test_model_to_dict_remains_free_of_persistence_integrity_metadata():
    assert "integrity" not in ProjectDocument(name="Mutable model snapshot").to_dict()


def test_atomic_write_text_syncs_parent_directory(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(
        project_module,
        "_fsync_directory",
        lambda directory: calls.append(directory),
    )

    target = atomic_write_text(tmp_path / "durable.txt", "payload\n")

    assert target.read_text(encoding="utf-8") == "payload\n"
    assert calls == [tmp_path]


def test_save_project_document_detects_failed_read_back_verification(
    tmp_path, monkeypatch
):
    def corrupting_write(path, text):
        destination = project_module.Path(path)
        raw = json.loads(text)
        raw["project"]["name"] = "Corrupted after serialization"
        destination.write_text(json.dumps(raw) + "\n", encoding="utf-8")
        return destination

    monkeypatch.setattr(project_module, "atomic_write_text", corrupting_write)

    with pytest.raises(ProjectFormatError, match="read-back verification"):
        save_project_document(
            tmp_path / "readback.cleanroomx.json",
            ProjectDocument(name="Expected"),
        )
