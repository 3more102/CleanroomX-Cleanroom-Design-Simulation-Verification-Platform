from __future__ import annotations

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


# CleanroomX only uses the native IFC parser, geometry bridge, and four utility
# modules below. Keep collection bounded to that runtime surface so unrelated
# optional IfcOpenShell integrations are not imported during PyInstaller analysis.
datas = collect_data_files("ifcopenshell")
binaries = collect_dynamic_libs(
    "ifcopenshell",
    search_patterns=["*.dll", "*.pyd", "*.so", "*.so.*", "*.dylib"],
)
hiddenimports = [
    "ifcopenshell.ifcopenshell_wrapper",
    "ifcopenshell.geom",
    "ifcopenshell.geom.main",
    "ifcopenshell.util.element",
    "ifcopenshell.util.placement",
    "ifcopenshell.util.shape",
    "ifcopenshell.util.unit",
]
