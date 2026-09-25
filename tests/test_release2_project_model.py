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
