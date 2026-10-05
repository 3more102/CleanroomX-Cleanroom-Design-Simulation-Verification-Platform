import hashlib

import pytest

ifcopenshell = pytest.importorskip(
    "ifcopenshell",
    reason="native IFC smoke requires the optional CleanroomX BIM dependency",
)

import ifcopenshell.api.root
import ifcopenshell.api.unit

from cleanroomx.bim_ifc import extract_ifc_semantics


def test_native_ifcopenshell_parser_smoke(tmp_path):
    source = tmp_path / "native-smoke.ifc"
    model = ifcopenshell.file(schema="IFC4")
    ifcopenshell.api.root.create_entity(model, ifc_class="IfcProject")
    length_unit = ifcopenshell.api.unit.add_si_unit(
        model,
        unit_type="LENGTHUNIT",
    )
    ifcopenshell.api.unit.assign_unit(model, units=[length_unit])
    model.write(str(source))

    payload = source.read_bytes()
    semantics, provenance = extract_ifc_semantics(source)

    assert semantics["records"] == []
    assert provenance == {
        "source_name": source.name,
        "source_sha256": hashlib.sha256(payload).hexdigest(),
    }
