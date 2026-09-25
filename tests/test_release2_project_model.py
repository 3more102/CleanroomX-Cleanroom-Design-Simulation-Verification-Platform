from __future__ import annotations

from cleanroomx.project import AnalysisDocument, ProjectDocument, project_from_dict


def test_release2_project_model_detaches_input_metadata_and_extensions():
    payload = {"nested": {"value": 1}}
    metadata = {"owner": {"name": "A"}}
    analysis_extra = {"vendor": {"tag": "x"}}
    project_extra = {"site": {"zone": 2}}
    top_extra = {"extension": {"enabled": True}}

    analysis = AnalysisDocument(
        id="analysis-a",
        name="A",
        kind="room_verification",
        input=payload,
        extra_fields=analysis_extra,
    )
    project = ProjectDocument(
        name="P",
        analyses=[analysis],
        active_analysis_id="analysis-a",
        metadata=metadata,
        project_extra_fields=project_extra,
        top_level_extra_fields=top_extra,
    )

    payload["nested"]["value"] = 99
    metadata["owner"]["name"] = "mutated"
    analysis_extra["vendor"]["tag"] = "mutated"
    project_extra["site"]["zone"] = 99
    top_extra["extension"]["enabled"] = False

    assert analysis.input["nested"]["value"] == 1
    assert project.metadata["owner"]["name"] == "A"

    snapshot = project.to_dict()
    snapshot["analyses"][0]["input"]["nested"]["value"] = 77
    snapshot["analyses"][0]["vendor"]["tag"] = "changed"
    snapshot["project"]["metadata"]["owner"]["name"] = "changed"
    snapshot["project"]["site"]["zone"] = 77
    snapshot["extension"]["enabled"] = False

    assert analysis.input["nested"]["value"] == 1
    assert analysis.extra_fields["vendor"]["tag"] == "x"
    assert project.metadata["owner"]["name"] == "A"
    assert project.project_extra_fields["site"]["zone"] == 2
    assert project.top_level_extra_fields["extension"]["enabled"] is True


def test_release2_supported_extensions_survive_parse_serialize_parse():
    raw = {
        "schema": "cleanroomx.project",
        "schema_version": 1,
        "application_version": "future-compatible",
        "extension": {"nested": [1, {"k": "v"}]},
        "project": {
            "name": "P",
            "description": "",
            "metadata": {},
            "site_extension": {"class": "ISO 7"},
        },
        "analyses": [{
            "id": "analysis-a",
            "name": "A",
            "kind": "room_verification",
            "input": {},
            "analysis_extension": {"authority": "lab"},
        }],
        "active_analysis_id": "analysis-a",
    }
    first = project_from_dict(raw)
    encoded = first.to_dict()
    second = project_from_dict(encoded)
    assert second.to_dict()["extension"] == raw["extension"]
    assert second.to_dict()["project"]["site_extension"] == raw["project"]["site_extension"]
    assert second.to_dict()["analyses"][0]["analysis_extension"] == raw["analyses"][0]["analysis_extension"]


def test_release2_analysis_lifecycle_uses_full_unique_uuid_ids():
    project = ProjectDocument(name="P")
    first = project.create_analysis(kind="room_verification", name="A")
    second = project.create_analysis(kind="room_verification", name="B")
    assert first.id.startswith("room_verification-")
    assert second.id.startswith("room_verification-")
    assert len(first.id.split("-", 1)[1]) == 32
    assert first.id != second.id
    assert project.analysis_by_id(first.id) is first
    removed = project.remove_analysis(first.id)
    assert removed is first
    assert project.active_analysis_id == second.id


def test_release2_project_model_rejects_non_json_keys_and_non_finite_values():
    import math
    import pytest
    from cleanroomx.project import ProjectFormatError

    with pytest.raises(ProjectFormatError):
        ProjectDocument(name="P", metadata={1: "coerced"})
    with pytest.raises(ProjectFormatError):
        AnalysisDocument(
            id="a",
            name="A",
            kind="room_verification",
            input={"value": math.inf},
        )


def test_release2_strict_loader_rejects_duplicate_object_keys(tmp_path):
    import pytest
    from cleanroomx.project import ProjectFormatError, load_project_document

    path = tmp_path / "dup.cleanroomx.json"
    path.write_text(
        '{"schema":"cleanroomx.project","schema_version":1,'
        '"project":{"name":"P","name":"Q","description":"","metadata":{}},'
        '"analyses":[],"active_analysis_id":null}',
        encoding="utf-8",
    )
    with pytest.raises(ProjectFormatError):
        load_project_document(path)
