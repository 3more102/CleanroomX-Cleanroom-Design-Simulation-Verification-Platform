import copy
import sys
import types

import pytest

import cleanroomx.bim_ifc as bim_ifc_module

from cleanroomx.bim_ifc import (
    IFC_LINK_METADATA_KEY,
    IfcImportError,
    apply_ifc_semantics_to_project,
    extract_ifc_semantics,
    layout_from_ifc_semantics,
    normalize_ifc_semantic_records,
    plan_ifc_semantic_reimport,
    reimport_ifc_semantics_to_project,
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



def _install_empty_ifcopenshell(monkeypatch):
    class Model:
        def by_type(self, _ifc_class, include_subtypes=True):
            return []

    ifcopenshell = types.ModuleType("ifcopenshell")
    ifcopenshell.__path__ = []
    ifcopenshell.open = lambda _path: Model()

    util = types.ModuleType("ifcopenshell.util")
    util.__path__ = []
    element = types.ModuleType("ifcopenshell.util.element")
    placement = types.ModuleType("ifcopenshell.util.placement")
    unit = types.ModuleType("ifcopenshell.util.unit")
    unit.calculate_unit_scale = lambda _model: 1.0

    ifcopenshell.util = util
    util.element = element
    util.placement = placement
    util.unit = unit
    monkeypatch.setitem(sys.modules, "ifcopenshell", ifcopenshell)
    monkeypatch.setitem(sys.modules, "ifcopenshell.util", util)
    monkeypatch.setitem(sys.modules, "ifcopenshell.util.element", element)
    monkeypatch.setitem(sys.modules, "ifcopenshell.util.placement", placement)
    monkeypatch.setitem(sys.modules, "ifcopenshell.util.unit", unit)



@pytest.mark.parametrize(
    ("predefined_type", "expected"),
    [
        ("DIFFUSER", "supply"),
        ("LINEARDIFFUSER", "supply"),
        ("SUPPLYAIR", "supply"),
        ("RETURNAIR", "return"),
        ("EXHAUSTAIR", "exhaust"),
        ("GRILLE", "equipment"),
        ("REGISTER", "equipment"),
        ("LOUVRE", "equipment"),
        ("USERDEFINED", "equipment"),
        ("NOTDEFINED", "equipment"),
        ("", "equipment"),
    ],
)
def test_ifc_air_terminal_role_mapping_is_fail_closed(
    predefined_type, expected
):
    assert (
        bim_ifc_module._device_type("IfcAirTerminal", predefined_type)
        == expected
    )


def test_ambiguous_ifc_air_terminal_stays_generic_equipment():
    records = _records()
    records[1]["predefined_type"] = "GRILLE"

    semantics = normalize_ifc_semantic_records(records)
    layout = layout_from_ifc_semantics(semantics)

    assert layout["devices"][0]["type"] == "equipment"


@pytest.mark.parametrize(
    "predefined_type",
    ["", "SUPPLYAIR", "RETURNAIR", "EXHAUSTAIR", "DIFFUSER", "USERDEFINED"],
)
def test_generic_ifc_flow_terminal_role_mapping_is_fail_closed(predefined_type):
    assert (
        bim_ifc_module._device_type("IfcFlowTerminal", predefined_type)
        == "equipment"
    )


def test_generic_ifc_flow_terminal_stays_generic_equipment_in_layout():
    records = _records()
    records[1]["ifc_class"] = "IfcFlowTerminal"
    records[1]["predefined_type"] = "SUPPLYAIR"

    semantics = normalize_ifc_semantic_records(records)
    layout = layout_from_ifc_semantics(semantics)

    assert layout["devices"][0]["type"] == "equipment"

def test_ifc_placement_uses_full_ifcopenshell_transform_matrix():
    entity = types.SimpleNamespace(
        GlobalId="SPACE-ROTATED",
        ObjectPlacement=object(),
    )

    class PlacementUtil:
        @staticmethod
        def get_local_placement(_placement):
            return (
                (0.0, -1.0, 0.0, 1200.0),
                (1.0, 0.0, 0.0, 700.0),
                (0.0, 0.0, 1.0, 300.0),
                (0.0, 0.0, 0.0, 1.0),
            )

    assert bim_ifc_module._placement_xyz_m(
        entity, 0.001, PlacementUtil
    ) == pytest.approx((1.2, 0.7, 0.3))


def test_ifc_device_orientation_uses_world_placement_yaw():
    entity = types.SimpleNamespace(
        GlobalId="AT-ROTATED",
        ObjectPlacement=object(),
    )

    class PlacementUtil:
        @staticmethod
        def get_local_placement(_placement):
            return (
                (0.0, -1.0, 0.0, 1200.0),
                (1.0, 0.0, 0.0, 700.0),
                (0.0, 0.0, 1.0, 300.0),
                (0.0, 0.0, 0.0, 1.0),
            )

    assert bim_ifc_module._placement_orientation_deg(
        entity, PlacementUtil
    ) == pytest.approx(90.0)


def test_ifc_device_orientation_rejects_undefined_plan_axis():
    entity = types.SimpleNamespace(
        GlobalId="AT-VERTICAL-X",
        ObjectPlacement=object(),
    )

    class PlacementUtil:
        @staticmethod
        def get_local_placement(_placement):
            return (
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )

    with pytest.raises(IfcImportError, match="no usable plan orientation"):
        bim_ifc_module._placement_orientation_deg(entity, PlacementUtil)


def test_ifc_cleanroomx_space_pset_maps_only_explicit_semantic_fields():
    space = types.SimpleNamespace(GlobalId="SPACE-PSET")
    calls = []

    class ElementUtil:
        @staticmethod
        def get_pset(entity, name, *, psets_only, should_inherit):
            calls.append((entity, name, psets_only, should_inherit))
            return {
                "Classification": "ISO 7",
                "AnalysisRoomName": "Process",
                "Unrelated": "ignored",
                "id": 42,
            }

    metadata = bim_ifc_module._cleanroomx_space_metadata(space, ElementUtil)

    assert metadata == {
        "classification": "ISO 7",
        "analysis_room_name": "Process",
    }
    assert calls == [(space, "CleanroomX_Space", True, True)]


def test_ifc_cleanroomx_space_pset_rejects_malformed_payload():
    space = types.SimpleNamespace(GlobalId="SPACE-PSET-BAD")

    class ElementUtil:
        @staticmethod
        def get_pset(*_args, **_kwargs):
            return "not-a-property-mapping"

    with pytest.raises(IfcImportError, match="must be a property mapping"):
        bim_ifc_module._cleanroomx_space_metadata(space, ElementUtil)


def test_ifc_extraction_queries_generic_flow_terminal_without_subtypes(
    monkeypatch, tmp_path
):
    _install_empty_ifcopenshell(monkeypatch)
    calls = []

    class Model:
        def by_type(self, ifc_class, include_subtypes=True):
            calls.append((ifc_class, include_subtypes))
            return []

    ifcopenshell = sys.modules["ifcopenshell"]
    ifcopenshell.open = lambda _path: Model()

    source = tmp_path / "facility.ifc"
    source.write_text("IFC", encoding="utf-8")

    semantics, _ = extract_ifc_semantics(source)

    assert semantics["records"] == []
    assert ("IfcAirTerminal", True) in calls
    assert ("IfcFlowTerminal", False) in calls


def test_ifc_extraction_preserves_device_world_orientation(monkeypatch, tmp_path):
    _install_empty_ifcopenshell(monkeypatch)

    entity = types.SimpleNamespace(
        GlobalId="AT-EXTRACT",
        Name="Supply rotated",
        PredefinedType="SUPPLYAIR",
        ObjectPlacement=object(),
        ContainedInStructure=(),
        OverallWidth=None,
        OverallHeight=None,
    )

    class Model:
        def by_type(self, ifc_class):
            if ifc_class == "IfcAirTerminal":
                return [entity]
            return []

    ifcopenshell = sys.modules["ifcopenshell"]
    ifcopenshell.open = lambda _path: Model()
    placement = sys.modules["ifcopenshell.util.placement"]
    placement.get_local_placement = lambda _placement: (
        (0.0, -1.0, 0.0, 1000.0),
        (1.0, 0.0, 0.0, 2000.0),
        (0.0, 0.0, 1.0, 2800.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    element = sys.modules["ifcopenshell.util.element"]
    element.get_container = lambda *_args, **_kwargs: None
    unit = sys.modules["ifcopenshell.util.unit"]
    unit.calculate_unit_scale = lambda _model: 0.001

    source = tmp_path / "facility.ifc"
    source.write_text("IFC", encoding="utf-8")

    semantics, _ = extract_ifc_semantics(source)

    assert len(semantics["records"]) == 1
    record = semantics["records"][0]
    assert record["global_id"] == "AT-EXTRACT"
    assert record["ifc_class"] == "IfcAirTerminal"
    assert record["name"] == "Supply rotated"
    assert record["predefined_type"] == "SUPPLYAIR"
    assert (record["x_m"], record["y_m"], record["z_m"]) == pytest.approx(
        (1.0, 2.0, 2.8)
    )
    assert record["orientation_deg"] == pytest.approx(90.0)


def test_ifc_placement_rejects_invalid_transform_values():
    entity = types.SimpleNamespace(
        GlobalId="SPACE-BAD",
        ObjectPlacement=object(),
    )

    class PlacementUtil:
        @staticmethod
        def get_local_placement(_placement):
            return (
                (1.0, 0.0, 0.0, float("nan")),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )

    with pytest.raises(IfcImportError, match="placement_x must be a finite number"):
        bim_ifc_module._placement_xyz_m(entity, 1.0, PlacementUtil)


def test_ifc_space_container_resolution_uses_indirect_ifcopenshell_container():
    class Space:
        GlobalId = "SPACE-INDIRECT"

        @staticmethod
        def is_a(name):
            return name == "IfcSpace"

    calls = []

    class ElementUtil:
        @staticmethod
        def get_container(entity, *, should_get_direct, ifc_class):
            calls.append((entity, should_get_direct, ifc_class))
            return Space()

    entity = types.SimpleNamespace(
        GlobalId="AT-INDIRECT",
        ContainedInStructure=(),
    )

    assert (
        bim_ifc_module._containing_space_global_id(entity, ElementUtil)
        == "SPACE-INDIRECT"
    )
    assert calls == [(entity, False, "IfcSpace")]


def test_ifc_space_container_resolution_prefers_explicit_space_relation():
    class Space:
        def __init__(self, global_id):
            self.GlobalId = global_id

        @staticmethod
        def is_a(name):
            return name == "IfcSpace"

    direct = Space("SPACE-DIRECT")

    class ElementUtil:
        @staticmethod
        def get_container(*_args, **_kwargs):
            raise AssertionError("fallback container lookup should not be used")

    entity = types.SimpleNamespace(
        GlobalId="AT-DIRECT",
        ContainedInStructure=(
            types.SimpleNamespace(RelatingStructure=direct),
        ),
    )

    assert (
        bim_ifc_module._containing_space_global_id(entity, ElementUtil)
        == "SPACE-DIRECT"
    )


def test_ifc_storey_metadata_uses_world_storey_elevation():
    space = types.SimpleNamespace(
        GlobalId="SPACE-LEVEL-1",
    )
    storey = types.SimpleNamespace(
        GlobalId="STOREY-01",
        Name="Level 1",
        LongName=None,
        ObjectPlacement=object(),
        Elevation=None,
        is_a=lambda name: name == "IfcBuildingStorey",
    )
    calls = []

    class ElementUtil:
        @staticmethod
        def get_aggregate(entity):
            calls.append(entity)
            return storey if entity is space else None

        @staticmethod
        def get_container(*_args, **_kwargs):
            raise AssertionError("aggregate hierarchy should resolve the storey")

    class PlacementUtil:
        @staticmethod
        def get_local_placement(_placement):
            return (
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 3000.0),
                (0.0, 0.0, 0.0, 1.0),
            )

    metadata = bim_ifc_module._containing_storey_metadata(
        space,
        0.001,
        ElementUtil,
        PlacementUtil,
    )

    assert metadata == {
        "storey_global_id": "STOREY-01",
        "storey_name": "Level 1",
        "storey_elevation_m": 3.0,
    }
    assert calls == [space]


def test_ifc_semantics_promote_one_explicit_storey_to_layout_floor():
    records = _records()
    records[0].update(
        {
            "z_m": 3.0,
            "storey_global_id": "STOREY-01",
            "storey_name": "Level 1",
            "storey_elevation_m": 3.0,
        }
    )

    semantics = normalize_ifc_semantic_records(records)
    layout = layout_from_ifc_semantics(semantics)

    assert layout["floor"] == {
        "id": "storey-01",
        "name": "Level 1",
        "elevation_m": 3.0,
        "default_ceiling_height_m": 3.0,
        "units": "m",
    }
    assert layout["rooms"][0]["floor_elevation_m"] == 3.0


def test_ifc_storey_metadata_requires_storey_global_id():
    records = _records()
    records[0]["storey_name"] = "Level 1"

    with pytest.raises(IfcImportError, match="storey_global_id is required"):
        normalize_ifc_semantic_records(records)


def test_ifc_semantics_reject_inconsistent_storey_metadata():
    records = _records()
    second_space = copy.deepcopy(records[0])
    second_space.update(
        {
            "global_id": "SPACE-002",
            "name": "ISO 8 Support",
            "storey_global_id": "STOREY-01",
            "storey_name": "Level One",
            "storey_elevation_m": 3.0,
        }
    )
    records[0].update(
        {
            "storey_global_id": "STOREY-01",
            "storey_name": "Level 1",
            "storey_elevation_m": 3.0,
        }
    )
    records.append(second_space)

    with pytest.raises(IfcImportError, match="inconsistent storey_name"):
        normalize_ifc_semantic_records(records)

    records[-1]["storey_name"] = "Level 1"
    records[-1]["storey_elevation_m"] = 3.2
    with pytest.raises(IfcImportError, match="inconsistent storey_elevation_m"):
        normalize_ifc_semantic_records(records)


def test_ifc_extraction_preserves_space_storey_identity(monkeypatch, tmp_path):
    _install_empty_ifcopenshell(monkeypatch)

    space_placement = object()
    storey_placement = object()
    space = types.SimpleNamespace(
        GlobalId="SPACE-LEVEL-1",
        LongName="Process",
        Name="Process",
        ObjectPlacement=space_placement,
    )
    storey = types.SimpleNamespace(
        GlobalId="STOREY-01",
        LongName=None,
        Name="Level 1",
        ObjectPlacement=storey_placement,
        Elevation=None,
        is_a=lambda name: name == "IfcBuildingStorey",
    )

    class Model:
        def by_type(self, ifc_class):
            if ifc_class == "IfcSpace":
                return [space]
            return []

    ifcopenshell = sys.modules["ifcopenshell"]
    ifcopenshell.open = lambda _path: Model()
    element = sys.modules["ifcopenshell.util.element"]
    element.get_psets = lambda *_args, **_kwargs: {
        "Qto_SpaceBaseQuantities": {
            "Length": 6000.0,
            "Width": 5000.0,
            "Height": 3000.0,
        }
    }
    element.get_pset = lambda *_args, **_kwargs: {
        "Classification": "ISO 7",
        "AnalysisRoomName": "Process",
    }

    def get_aggregate(entity):
        if entity is space:
            return storey
        return None

    element.get_aggregate = get_aggregate
    element.get_container = lambda *_args, **_kwargs: None
    placement = sys.modules["ifcopenshell.util.placement"]

    def get_local_placement(value):
        if value is space_placement:
            return (
                (1.0, 0.0, 0.0, 1000.0),
                (0.0, 1.0, 0.0, 2000.0),
                (0.0, 0.0, 1.0, 3000.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        if value is storey_placement:
            return (
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 3000.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        raise AssertionError("unexpected placement")

    placement.get_local_placement = get_local_placement
    unit = sys.modules["ifcopenshell.util.unit"]
    unit.calculate_unit_scale = lambda _model: 0.001

    source = tmp_path / "facility.ifc"
    source.write_text("IFC", encoding="utf-8")

    semantics, _ = extract_ifc_semantics(source)

    space_record = semantics["records"][0]
    assert space_record["global_id"] == "SPACE-LEVEL-1"
    assert space_record["storey_global_id"] == "STOREY-01"
    assert space_record["storey_name"] == "Level 1"
    assert space_record["storey_elevation_m"] == pytest.approx(3.0)
    assert space_record["classification"] == "ISO 7"
    assert space_record["analysis_room_name"] == "Process"


def test_ifc_extraction_rejects_source_digest_drift(monkeypatch, tmp_path):
    _install_empty_ifcopenshell(monkeypatch)
    digests = iter(["a" * 64, "b" * 64])
    monkeypatch.setattr(
        bim_ifc_module,
        "_file_sha256",
        lambda _path: next(digests),
    )

    with pytest.raises(IfcImportError, match="changed while it was being read"):
        extract_ifc_semantics(tmp_path / "facility.ifc")


def test_ifc_extraction_binds_digest_only_after_stable_read(monkeypatch, tmp_path):
    _install_empty_ifcopenshell(monkeypatch)
    calls = []
    monkeypatch.setattr(
        bim_ifc_module,
        "_file_sha256",
        lambda path: calls.append(path) or "a" * 64,
    )

    semantics, provenance = extract_ifc_semantics(tmp_path / "facility.ifc")

    assert semantics["records"] == []
    assert provenance == {
        "source_name": "facility.ifc",
        "source_sha256": "a" * 64,
    }
    assert len(calls) == 2


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


@pytest.mark.parametrize(
    "ifc_class",
    ["IfcWall", "IfcBeam", "IfcBuildingElementProxy"],
)
def test_ifc_semantics_reject_unsupported_ifc_classes(ifc_class):
    records = _records()
    records[1]["ifc_class"] = ifc_class

    with pytest.raises(IfcImportError, match="is not supported"):
        normalize_ifc_semantic_records(records)


def test_device_type_rejects_unknown_ifc_device_class():
    with pytest.raises(IfcImportError, match="unsupported IFC device class"):
        bim_ifc_module._device_type("IfcWall")


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
    space = next(
        record
        for record in semantics["records"]
        if record["ifc_class"] == "IfcSpace"
    )
    space["length_m"] = 7.0

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


def test_ifc_import_persists_global_id_bindings_for_future_reimport():
    project = new_project("IFC Project")
    semantics = normalize_ifc_semantic_records(_records())

    apply_ifc_semantics_to_project(
        project,
        semantics,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )

    link = project.metadata[IFC_LINK_METADATA_KEY]
    assert link["schema_version"] == 2
    assert len(link["bindings"]) == 3
    assert len(link["bindings_sha256"]) == 64
    by_global_id = {item["global_id"]: item for item in link["bindings"]}
    assert by_global_id["SPACE-001"]["kind"] == "room"
    assert by_global_id["SPACE-001"]["spatial_id"] == "iso-7-process"
    assert len(by_global_id["SPACE-001"]["source_spatial_sha256"]) == 64


def test_ifc_reimport_updates_source_change_without_changing_spatial_identity():
    project = new_project("IFC Project")
    original = normalize_ifc_semantic_records(_records())
    apply_ifc_semantics_to_project(
        project,
        original,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )
    room_id = project.metadata["spatial_layout"]["rooms"][0]["id"]

    changed_records = _records()
    changed_records[0]["name"] = "ISO 7 Process Revised"
    changed_records[0]["length_m"] = 6.5
    changed = normalize_ifc_semantic_records(changed_records)

    plan = plan_ifc_semantic_reimport(
        project,
        changed,
        source_name="facility-v2.ifc",
        source_sha256="b" * 64,
    )
    assert plan["can_apply"] is True
    space_change = next(
        item for item in plan["changes"] if item["global_id"] == "SPACE-001"
    )
    assert space_change["action"] == "update"

    report = reimport_ifc_semantics_to_project(
        project,
        changed,
        source_name="facility-v2.ifc",
        source_sha256="b" * 64,
    )
    assert report["can_apply"] is True
    room = project.metadata["spatial_layout"]["rooms"][0]
    assert room["id"] == room_id
    assert room["name"] == "ISO 7 Process Revised"
    assert room["length_m"] == 6.5
    assert project.metadata[IFC_LINK_METADATA_KEY]["source_sha256"] == "b" * 64


def test_ifc_reimport_preserves_local_only_edit_when_source_is_unchanged():
    project = new_project("IFC Project")
    semantics = normalize_ifc_semantic_records(_records())
    apply_ifc_semantics_to_project(
        project,
        semantics,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )
    project.metadata["spatial_layout"]["rooms"][0]["classification"] = "Local review"

    plan = plan_ifc_semantic_reimport(
        project,
        semantics,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )
    space_change = next(
        item for item in plan["changes"] if item["global_id"] == "SPACE-001"
    )
    assert space_change["action"] == "preserve_local"
    assert plan["can_apply"] is True

    reimport_ifc_semantics_to_project(
        project,
        semantics,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )
    assert (
        project.metadata["spatial_layout"]["rooms"][0]["classification"]
        == "Local review"
    )


def test_ifc_reimport_surfaces_semantic_only_source_change():
    project = new_project("IFC Project")
    original = normalize_ifc_semantic_records(_records())
    apply_ifc_semantics_to_project(
        project,
        original,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )
    before_layout = copy.deepcopy(project.metadata["spatial_layout"])
    old_binding = next(
        item
        for item in project.metadata[IFC_LINK_METADATA_KEY]["bindings"]
        if item["global_id"] == "AT-001"
    )
    old_record_digest = old_binding["record_sha256"]

    changed_records = _records()
    changed_records[1]["predefined_type"] = "DIFFUSER"
    changed = normalize_ifc_semantic_records(changed_records)

    plan = plan_ifc_semantic_reimport(
        project,
        changed,
        source_name="facility-v2.ifc",
        source_sha256="b" * 64,
    )
    terminal_change = next(
        item for item in plan["changes"] if item["global_id"] == "AT-001"
    )
    assert terminal_change["action"] == "semantic_update"
    assert terminal_change["source_changed"] is True
    assert terminal_change["source_semantic_changed"] is True
    assert terminal_change["source_spatial_changed"] is False
    assert plan["can_apply"] is True

    reimport_ifc_semantics_to_project(
        project,
        changed,
        source_name="facility-v2.ifc",
        source_sha256="b" * 64,
    )
    assert project.metadata["spatial_layout"] == before_layout
    new_binding = next(
        item
        for item in project.metadata[IFC_LINK_METADATA_KEY]["bindings"]
        if item["global_id"] == "AT-001"
    )
    assert new_binding["ifc_class"] == "IfcAirTerminal"
    assert new_binding["record_sha256"] != old_record_digest


def test_ifc_semantic_only_source_change_does_not_conflict_with_local_spatial_edit():
    project = new_project("IFC Project")
    original = normalize_ifc_semantic_records(_records())
    apply_ifc_semantics_to_project(
        project,
        original,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )
    supply = next(
        item
        for item in project.metadata["spatial_layout"]["devices"]
        if item["name"] == "Supply 01"
    )
    supply["z_m"] = 2.6

    changed_records = _records()
    changed_records[1]["predefined_type"] = "DIFFUSER"
    changed = normalize_ifc_semantic_records(changed_records)

    plan = plan_ifc_semantic_reimport(
        project,
        changed,
        source_name="facility-v2.ifc",
        source_sha256="b" * 64,
    )
    terminal_change = next(
        item for item in plan["changes"] if item["global_id"] == "AT-001"
    )
    assert terminal_change["action"] == "preserve_local"
    assert terminal_change["local_changed"] is True
    assert terminal_change["source_changed"] is True
    assert terminal_change["source_semantic_changed"] is True
    assert terminal_change["source_spatial_changed"] is False
    assert plan["can_apply"] is True

    reimport_ifc_semantics_to_project(
        project,
        changed,
        source_name="facility-v2.ifc",
        source_sha256="b" * 64,
    )
    supply = next(
        item
        for item in project.metadata["spatial_layout"]["devices"]
        if item["name"] == "Supply 01"
    )
    assert supply["z_m"] == 2.6


def test_ifc_reimport_detects_two_sided_conflict_and_is_transactional():
    project = new_project("IFC Project")
    original = normalize_ifc_semantic_records(_records())
    apply_ifc_semantics_to_project(
        project,
        original,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )
    project.metadata["spatial_layout"]["rooms"][0]["length_m"] = 6.25
    before = copy.deepcopy(project.metadata)

    changed_records = _records()
    changed_records[0]["length_m"] = 6.75
    changed = normalize_ifc_semantic_records(changed_records)

    plan = plan_ifc_semantic_reimport(
        project,
        changed,
        source_name="facility-v2.ifc",
        source_sha256="b" * 64,
    )
    space_change = next(
        item for item in plan["changes"] if item["global_id"] == "SPACE-001"
    )
    assert space_change["action"] == "conflict"
    assert plan["conflict_count"] == 1
    assert plan["can_apply"] is False

    with pytest.raises(IfcImportError, match="1 conflict"):
        reimport_ifc_semantics_to_project(
            project,
            changed,
            source_name="facility-v2.ifc",
            source_sha256="b" * 64,
        )
    assert project.metadata == before


def test_ifc_reimport_adds_and_removes_source_entities_without_losing_local_items():
    project = new_project("IFC Project")
    original = normalize_ifc_semantic_records(_records())
    apply_ifc_semantics_to_project(
        project,
        original,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )
    project.metadata["spatial_layout"]["devices"].append(
        {
            "id": "local-note-sensor",
            "type": "sensor",
            "name": "Local note sensor",
            "room_id": "iso-7-process",
            "x_m": 4.0,
            "y_m": 4.0,
            "z_m": 1.2,
            "orientation_deg": 0.0,
        }
    )

    changed_records = [
        record for record in _records() if record["global_id"] != "SENSOR-001"
    ]
    changed_records.append(
        {
            "global_id": "AT-002",
            "ifc_class": "IfcAirTerminal",
            "name": "Return 02",
            "room_global_id": "SPACE-001",
            "predefined_type": "RETURNAIR",
            "x_m": 5.0,
            "y_m": 4.0,
            "z_m": 2.8,
        }
    )
    changed = normalize_ifc_semantic_records(changed_records)

    plan = plan_ifc_semantic_reimport(
        project,
        changed,
        source_name="facility-v2.ifc",
        source_sha256="c" * 64,
    )
    actions = {item["global_id"]: item["action"] for item in plan["changes"]}
    assert actions["SENSOR-001"] == "remove"
    assert actions["AT-002"] == "add"
    assert plan["can_apply"] is True

    reimport_ifc_semantics_to_project(
        project,
        changed,
        source_name="facility-v2.ifc",
        source_sha256="c" * 64,
    )
    devices = {
        item["name"]: item for item in project.metadata["spatial_layout"]["devices"]
    }
    assert "DP Sensor" not in devices
    assert devices["Return 02"]["type"] == "return"
    assert "Local note sensor" in devices


def test_ifc_reimport_rejects_tampered_identity_bindings():
    project = new_project("IFC Project")
    semantics = normalize_ifc_semantic_records(_records())
    apply_ifc_semantics_to_project(
        project,
        semantics,
        source_name="facility.ifc",
        source_sha256="a" * 64,
    )
    project.metadata[IFC_LINK_METADATA_KEY]["bindings"][0]["spatial_id"] = "tampered"

    with pytest.raises(IfcImportError, match="binding digest"):
        plan_ifc_semantic_reimport(
            project,
            semantics,
            source_name="facility.ifc",
            source_sha256="a" * 64,
        )
