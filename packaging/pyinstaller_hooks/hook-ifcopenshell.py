from __future__ import annotations

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


# CleanroomX only uses the native IFC parser, geometry bridge, and four utility
# modules below. Do not use collect_all()/collect_submodules() here: importing
# the whole IfcOpenShell ecosystem makes the Windows freeze unnecessarily broad
# and can pull unrelated optional integrations into PyInstaller analysis.
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
