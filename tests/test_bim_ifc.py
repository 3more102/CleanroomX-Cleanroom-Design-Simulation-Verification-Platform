import copy

import pytest

from cleanroomx.bim_ifc import (
    IFC_LINK_METADATA_KEY,
    IfcImportError,
    apply_ifc_semantics_to_project,
    layout_from_ifc_semantics,
    normalize_ifc_semantic_records,
)
from cleanroomx.project import new_project, project_from_dict


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
            "classification": "ISO 7",
            "analysis_room_name": "Process",
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
        {
            "global_id": "SENSOR-001",
            "ifc_class": "IfcSensor",
            "name": "DP Sensor",
            "room_global_id": "SPACE-001",
            "x_m": 3.0,
            "y_m": 3.0,
            "z_m": 1.5,
        },
    ]


def test_ifc_semantics_are_deterministic_across_record_order():
    forward = normalize_ifc_semantic_records(_records())
    reverse = normalize_ifc_semantic_records(list(reversed(_records())))

    assert forward == reverse
    assert len(forward["semantic_sha256"]) == 64


def test_ifc_semantics_map_spaces_and_devices_into_spatial_layout():
    semantics = normalize_ifc_semantic_records(_records())
    layout = layout_from_ifc_semantics(semantics)

    assert layout["rooms"] == [
        {
            "id": "iso-7-process",
            "name": "ISO 7 Process",
            "x_m": 1.0,
            "y_m": 2.0,
            "length_m": 6.0,
            "width_m": 5.0,
            "height_m": 3.0,
            "floor_elevation_m": 0.0,
            "classification": "ISO 7",
            "analysis_room_name": "Process",
        }
    ]
    by_name = {item["name"]: item for item in layout["devices"]}
    assert by_name["Supply 01"]["type"] == "supply"
    assert by_name["Supply 01"]["room_id"] == "iso-7-process"
    assert by_name["DP Sensor"]["type"] == "sensor"


def test_ifc_semantics_reject_duplicate_ids_and_dangling_space_links():
    records = _records()
    records.append(copy.deepcopy(records[0]))
    with pytest.raises(IfcImportError, match="duplicate IFC GlobalId"):
        normalize_ifc_semantic_records(records)

    records = _records()
    records[1]["room_global_id"] = "MISSING-SPACE"
    with pytest.raises(IfcImportError, match="references missing space"):
        normalize_ifc_semantic_records(records)


def test_ifc_semantic_digest_detects_record_tampering():
    semantics = normalize_ifc_semantic_records(_records())
    semantics["records"][0]["length_m"] = 7.0

    with pytest.raises(IfcImportError, match="semantic digest"):
        layout_from_ifc_semantics(semantics)


def test_ifc_import_binds_source_and_semantics_to_project_metadata():
    project = new_project("IFC Project")
    semantics = normalize_ifc_semantic_records(_records())

    layout = apply_ifc_semantics_to_project(
        project,
        semantics,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )

    link = project.metadata[IFC_LINK_METADATA_KEY]
    assert link["source_name"] == "facility.ifc"
    assert link["source_sha256"] == "a" * 64
    assert link["semantic_sha256"] == semantics["semantic_sha256"]
    assert link["room_count"] == 1
    assert link["device_count"] == 2
    assert project.metadata["spatial_layout"] == layout

    restored = project_from_dict(project.to_dict())
    assert restored.metadata[IFC_LINK_METADATA_KEY] == link
    assert restored.metadata["spatial_layout"] == layout


def test_ifc_import_rejects_invalid_source_digest():
    project = new_project("IFC Project")
    semantics = normalize_ifc_semantic_records(_records())

    with pytest.raises(IfcImportError, match="source_sha256"):
        apply_ifc_semantics_to_project(
            project,
            semantics,
            source_name="facility.ifc",
            source_sha256="not-a-digest",
        )
