from __future__ import annotations

import argparse
from pathlib import Path
import struct
import tomllib


_ICON_SIZES = (16, 32, 48, 64, 128, 256)


def _project_version(repository_root: Path) -> str:
    metadata = tomllib.loads((repository_root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(metadata["project"]["version"])


def _numeric_version(version: str) -> tuple[int, int, int, int]:
    numbers: list[int] = []
    for token in version.replace("-", ".").split("."):
        digits = "".join(character for character in token if character.isdigit())
        if digits:
            numbers.append(int(digits))
        if len(numbers) == 4:
            break
    numbers.extend([0] * (4 - len(numbers)))
    numeric = tuple(numbers[:4])
    if any(value > 65535 for value in numeric):
        raise ValueError(f"Windows version component exceeds 65535: {version}")
    return numeric  # type: ignore[return-value]


def _icon_pixel(size: int, x: int, y: int) -> tuple[int, int, int, int]:
    scale = max(1, size // 18)
    distance = abs(x - (size - 1) / 2) + abs(y - (size - 1) / 2)
    lift = int(max(0.0, 18.0 - distance * 24.0 / max(1, size)))
    red, green, blue = 18 + lift, 31 + lift, 48 + lift
    if abs(x - y) <= scale or abs((size - 1 - x) - y) <= scale:
        red, green, blue = 37, 211, 235

    inset = max(1, size // 12)
    edge = max(1, size // 32)
    if (
        inset <= x < size - inset
        and inset <= y < size - inset
        and (
            x < inset + edge
            or x >= size - inset - edge
            or y < inset + edge
            or y >= size - inset - edge
        )
    ):
        red, green, blue = 131, 229, 245
    return blue, green, red, 255


def _dib_icon_image(size: int) -> bytes:
    pixels = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            pixels.extend(_icon_pixel(size, x, y))
    mask_row_bytes = ((size + 31) // 32) * 4
    mask = bytes(mask_row_bytes * size)
    bitmap_info = struct.pack(
        "<IIIHHIIIIII", 40, size, size * 2, 1, 32, 0, len(pixels), 0, 0, 0, 0
    )
    return bitmap_info + bytes(pixels) + mask


def _write_icon(path: Path) -> None:
    images = [(size, _dib_icon_image(size)) for size in _ICON_SIZES]
    offset = 6 + 16 * len(images)
    entries = bytearray()
    payload = bytearray()
    for size, image in images:
        dimension = 0 if size == 256 else size
        entries.extend(
            struct.pack("<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(image), offset)
        )
        payload.extend(image)
        offset += len(image)
    path.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + bytes(entries) + bytes(payload))


def _write_version_file(path: Path, version: str) -> None:
    major, minor, patch, build = _numeric_version(version)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({major}, {minor}, {patch}, {build}),
    prodvers=({major}, {minor}, {patch}, {build}),
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
    path.write_text(text, encoding="utf-8", newline="\n")


def build_resources(output_dir: Path, *, version: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    icon_path = output_dir / "cleanroomx.ico"
    version_path = output_dir / "file_version_info.txt"
    _write_icon(icon_path)
    _write_version_file(version_path, version)
    return icon_path, version_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build deterministic Windows packaging resources.")
    parser.add_argument("--output-dir", default="build/windows")
    parser.add_argument("--version")
    args = parser.parse_args(argv)
    repository_root = Path(__file__).resolve().parents[1]
    version = args.version or _project_version(repository_root)
    icon_path, version_path = build_resources(repository_root / args.output_dir, version=version)
    print(icon_path)
    print(version_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
