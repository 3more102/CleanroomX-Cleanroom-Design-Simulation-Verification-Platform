from __future__ import annotations

import json
import sys

import pytest

from cleanroomx import cfd_pipeline_cli
from cleanroomx.cfd_openfoam import build_openfoam_files, export_openfoam_cases
from cleanroomx.cfd_project_handoff import project_room_openfoam_spec
from cleanroomx.project import new_project, save_project_document
from cleanroomx.spatial import empty_layout
from cleanroomx.spatial_integrity import SPATIAL_METADATA_KEY
from cleanroomx.strict_json import load_strict_json


def _template_spec() -> dict:
    return load_strict_json("examples/cfd_openfoam_spec.example.json")


def _layout() -> dict:
    layout = empty_layout()
    layout["rooms"] = [
        {
            "id": "process-room",
            "name": "Process Room",
            "x_m": 0.0,
            "y_m": 0.0,
            "length_m": 8.0,
            "width_m": 6.0,
            "height_m": 3.2,
            "floor_elevation_m": 0.0,
        }
    ]
    return layout


def test_project_room_handoff_copies_only_dimensions_and_records_scope():
    template = _template_spec()
    original_template_dimensions = list(template["room_m"])

    spec = project_room_openfoam_spec(
        template,
        project_name="North Cleanroom",
        spatial_layout=_layout(),
        selection_kind="room",
        selected_room_id="process-room",
    )

    assert spec["room_m"] == [8.0, 6.0, 3.2]
    assert template["room_m"] == original_template_dimensions
    assert spec["name"] == "North Cleanroom — Process Room"
    assert spec["supply_flow_m3_s"] == template["supply_flow_m3_s"]
    assert spec["mesh_cells"] == template["mesh_cells"]
    assert spec["project_geometry"]["mapping"] == "rectangular_room_envelope_only"
    assert "doors and transfer openings" in spec["project_geometry"]["omitted"]

    _, metadata = build_openfoam_files(spec, 1)
    assert metadata["project_geometry"] == spec["project_geometry"]
    assert "omitted geometry" in metadata["limitations"][-1]


@pytest.mark.parametrize(
    ("selection_kind", "room_id", "layout", "match"),
    [
        ("device", "process-room", _layout(), "select a room"),
        ("room", "missing", _layout(), "missing or ambiguous"),
        (
            "room",
            "process-room",
            {**_layout(), "version": 99},
            "layout version",
        ),
        (
            "room",
            "process-room",
            {
                "version": 1,
                "rooms": [
                    {**_layout()["rooms"][0], "length_m": float("nan")}
                ],
            },
            "finite and positive",
        ),
    ],
)
def test_project_room_handoff_rejects_unsafe_layout_inputs(
    selection_kind, room_id, layout, match
):
    with pytest.raises(ValueError, match=match):
        project_room_openfoam_spec(
            _template_spec(),
            project_name="North Cleanroom",
            spatial_layout=layout,
            selection_kind=selection_kind,
            selected_room_id=room_id,
        )


def test_openfoam_spec_validation_rejects_mismatched_project_dimensions():
    spec = project_room_openfoam_spec(
        _template_spec(),
        project_name="North Cleanroom",
        spatial_layout=_layout(),
        selection_kind="room",
        selected_room_id="process-room",
    )
    spec["project_geometry"]["dimensions_m"][0] = 9.0

    with pytest.raises(ValueError, match="do not match room_m"):
        build_openfoam_files(spec, 1)


def test_project_room_spec_cli_saves_a_template_based_draft(tmp_path, monkeypatch):
    project = new_project("North Cleanroom")
    project.metadata[SPATIAL_METADATA_KEY] = _layout()
    project_path = tmp_path / "north.cleanroomx.json"
    save_project_document(project_path, project)
    template_path = tmp_path / "template.json"
    template_path.write_text(
        json.dumps(_template_spec(), sort_keys=True) + "\n", encoding="utf-8"
    )
    output = tmp_path / "north-room-spec.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-cfd-pipeline",
            "project-room-spec",
            str(project_path),
            str(template_path),
            "--room-id",
            "process-room",
            "--output",
            str(output),
        ],
    )

    assert cfd_pipeline_cli.main() == 0
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["room_m"] == [8.0, 6.0, 3.2]
    assert saved["project_geometry"]["room_id"] == "process-room"
    assert saved["supply_flow_m3_s"] == _template_spec()["supply_flow_m3_s"]


def test_project_room_spec_cli_will_not_overwrite_template_input(
    tmp_path, monkeypatch, capsys
):
    project = new_project("North Cleanroom")
    project.metadata[SPATIAL_METADATA_KEY] = _layout()
    project_path = tmp_path / "north.cleanroomx.json"
    save_project_document(project_path, project)
    template_path = tmp_path / "template.json"
    template_path.write_text(
        json.dumps(_template_spec(), sort_keys=True) + "\n", encoding="utf-8"
    )
    before = template_path.read_bytes()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-cfd-pipeline",
            "project-room-spec",
            str(project_path),
            str(template_path),
            "--room-id",
            "process-room",
            "--output",
            str(template_path),
        ],
    )

    assert cfd_pipeline_cli.main() == 1
    assert template_path.read_bytes() == before
    assert "output path must be different" in capsys.readouterr().err


def test_project_room_spec_cli_will_not_overwrite_template_hardlink(
    tmp_path, monkeypatch, capsys
):
    project = new_project("North Cleanroom")
    project.metadata[SPATIAL_METADATA_KEY] = _layout()
    project_path = tmp_path / "north.cleanroomx.json"
    save_project_document(project_path, project)
    template_path = tmp_path / "template.json"
    template_path.write_text(
        json.dumps(_template_spec(), sort_keys=True) + "\n", encoding="utf-8"
    )
    hardlink = tmp_path / "template-alias.json"
    try:
        hardlink.hardlink_to(template_path)
    except OSError as exc:
        pytest.skip(f"hard links are unavailable: {exc}")
    before = template_path.read_bytes()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "cleanroomx-cfd-pipeline",
            "project-room-spec",
            str(project_path),
            str(template_path),
            "--room-id",
            "process-room",
            "--output",
            str(hardlink),
        ],
    )

    assert cfd_pipeline_cli.main() == 1
    assert template_path.read_bytes() == before
    assert "output path must be different" in capsys.readouterr().err
