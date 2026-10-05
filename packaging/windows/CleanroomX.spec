# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve().parents[1]
BIM_DATAS, BIM_BINARIES, BIM_HIDDENIMPORTS = collect_all("ifcopenshell")
HIDDENIMPORTS = sorted(set(collect_submodules("cleanroomx") + BIM_HIDDENIMPORTS))
DATAS = [
    (str(ROOT / "src" / "cleanroomx" / "demo"), "cleanroomx/demo"),
    *copy_metadata("cleanroomx"),
    *BIM_DATAS,
]

a = Analysis(
    [str(ROOT / "packaging" / "windows" / "cleanroomx_desktop.py")],
    pathex=[str(ROOT / "src")],
    binaries=BIM_BINARIES,
    datas=DATAS,
    hiddenimports=HIDDENIMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CleanroomX",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(ROOT / "packaging" / "windows" / "cleanroomx.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="CleanroomX",
)
