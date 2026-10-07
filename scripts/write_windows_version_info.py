from __future__ import annotations

import argparse
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def project_version() -> str:
    with PYPROJECT.open("rb") as handle:
        payload = tomllib.load(handle)
    version = payload.get("project", {}).get("version")
    if not isinstance(version, str) or not version.strip():
        raise ValueError("pyproject.toml does not define a non-empty project.version")
    return version.strip()


def numeric_version(version: str) -> tuple[int, int, int, int]:
    release = version.split(".", 3)
    if len(release) < 3:
        raise ValueError(f"project version must begin with major.minor.patch: {version!r}")
    numeric: list[int] = []
    for part in release[:3]:
        digits = []
        for char in part:
            if char.isdigit():
                digits.append(char)
            else:
                break
        if not digits:
            raise ValueError(
                f"project version has a non-numeric release component: {version!r}"
            )
        numeric.append(int("".join(digits)))
    return numeric[0], numeric[1], numeric[2], 0


def render_version_info(version: str) -> str:
    version_tuple = numeric_version(version)
    tuple_text = ", ".join(str(value) for value in version_tuple)
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({tuple_text}),
    prodvers=({tuple_text}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', 'CleanroomX contributors'),
          StringStruct('FileDescription', 'CleanroomX Engineering Workstation'),
          StringStruct('FileVersion', '{version}'),
          StringStruct('InternalName', 'CleanroomX'),
          StringStruct('OriginalFilename', 'CleanroomX.exe'),
          StringStruct('ProductName', 'CleanroomX'),
          StringStruct('ProductVersion', '{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Write deterministic PyInstaller Windows version metadata."
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    version = project_version()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        render_version_info(version),
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
