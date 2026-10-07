from __future__ import annotations

import sys
import types

import pytest

from cleanroomx.bim_ifc import IfcImportError, extract_ifc_semantics


def _install_ifcopenshell(monkeypatch, model, *, unit_scale=1.0, unit_error=None):
    ifcopenshell = types.ModuleType("ifcopenshell")
    ifcopenshell.__path__ = []
    ifcopenshell.open = lambda _path: model

    util = types.ModuleType("ifcopenshell.util")
    util.__path__ = []
    element = types.ModuleType("ifcopenshell.util.element")
    placement = types.ModuleType("ifcopenshell.util.placement")
    unit = types.ModuleType("ifcopenshell.util.unit")

    def calculate_unit_scale(_model):
        if unit_error is not None:
            raise unit_error
        return unit_scale

    unit.calculate_unit_scale = calculate_unit_scale
    ifcopenshell.util = util
    util.element = element
    util.placement = placement
    util.unit = unit

    monkeypatch.setitem(sys.modules, "ifcopenshell", ifcopenshell)
    monkeypatch.setitem(sys.modules, "ifcopenshell.util", util)
    monkeypatch.setitem(sys.modules, "ifcopenshell.util.element", element)
    monkeypatch.setitem(sys.modules, "ifcopenshell.util.placement", placement)
    monkeypatch.setitem(sys.modules, "ifcopenshell.util.unit", unit)


def test_ifc_extraction_normalizes_unit_scale_parser_failure(monkeypatch, tmp_path):
    class Model:
        def by_type(self, _ifc_class):
            return []

    _install_ifcopenshell(
        monkeypatch,
        Model(),
        unit_error=RuntimeError("malformed IFC units"),
    )
    source = tmp_path / "facility.ifc"
    source.write_bytes(b"IFC")

    with pytest.raises(IfcImportError, match="unable to resolve IFC length unit scale") as exc:
        extract_ifc_semantics(source)

    assert isinstance(exc.value.__cause__, RuntimeError)


def test_ifc_extraction_fails_closed_when_space_enumeration_raises(monkeypatch, tmp_path):
    class Model:
        def by_type(self, ifc_class):
            if ifc_class == "IfcSpace":
                raise RuntimeError("malformed IFC spatial index")
            return []

    _install_ifcopenshell(monkeypatch, Model())
    source = tmp_path / "facility.ifc"
    source.write_bytes(b"IFC")

    with pytest.raises(IfcImportError, match="unable to enumerate IFC spaces") as exc:
        extract_ifc_semantics(source)

    assert isinstance(exc.value.__cause__, RuntimeError)


def test_ifc_extraction_fails_closed_when_device_enumeration_raises(monkeypatch, tmp_path):
    class Model:
        def by_type(self, ifc_class, include_subtypes=True):
            if ifc_class == "IfcAirTerminal":
                raise RuntimeError("malformed IFC device index")
            return []

    _install_ifcopenshell(monkeypatch, Model())
    source = tmp_path / "facility.ifc"
    source.write_bytes(b"IFC")

    with pytest.raises(
        IfcImportError,
        match=r"unable to enumerate IFC device entities for 'IfcAirTerminal'",
    ) as exc:
        extract_ifc_semantics(source)

    assert isinstance(exc.value.__cause__, RuntimeError)


def test_ifc_extraction_accepts_device_class_missing_from_older_schema(
    monkeypatch, tmp_path
):
    class Model:
        def by_type(self, ifc_class, include_subtypes=True):
            if ifc_class == "IfcFan":
                raise RuntimeError(
                    "Entity with name 'IfcFan' not found in schema 'IFC2X3'"
                )
            return []

    _install_ifcopenshell(monkeypatch, Model())
    source = tmp_path / "facility.ifc"
    source.write_bytes(b"IFC")

    semantics, provenance = extract_ifc_semantics(source)

    assert semantics["records"] == []
    assert provenance["source_name"] == "facility.ifc"
