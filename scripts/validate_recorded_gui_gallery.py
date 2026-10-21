#!/usr/bin/env python3
"""Verify the 2026-10-21 real GUI screenshot archive without CFD fabrication.

Only verifies archive bytes, PNG structure, source identity and documentation
references. It does not establish physical convergence or engineering release.
"""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
GALLERY = Path("docs/real-gui-screenshots-20261021")
MANIFEST = Path("reports/engineering-session-20261021/capture-manifest.json")
EXPECTED_NAMES = tuple(
    f"{index:02d}-{name}.png"
    for index, name in enumerate((
        "main-workspace", "design-studio", "multiroom-design", "object-inspector",
        "simulation-workspace", "original-openfoam-mesh", "computed-velocity-section",
        "pressure-and-airflow", "particle-injection", "computed-particle-tracking",
        "residual-graphs", "iteration-analysis", "particle-population",
        "3d-review-controls", "computed-3d-velocity", "computed-3d-pressure",
        "particle-source-closeup",
    ), 1)
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
EXPECTED_DUPLICATE = ("05-simulation-workspace.png", "08-pressure-and-airflow.png")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _unique_json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key in capture manifest: {key}")
        result[key] = value
    return result


def _png_dimensions(data: bytes, name: str) -> tuple[int, int]:
    _require(len(data) >= 57 and data[:8] == PNG_SIGNATURE,
             f"{name}: invalid PNG signature or truncated image")
    offset = 8
    first = True
    dimensions = None
    idat_found = False
    finished = False
    while offset < len(data):
        _require(len(data) - offset >= 12, f"{name}: truncated PNG chunk")
        length = struct.unpack_from(">I", data, offset)[0]
        end = offset + 12 + length
        _require(end <= len(data), f"{name}: PNG chunk exceeds file")
        tag = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + length]
        stored = struct.unpack_from(">I", data, offset + 8 + length)[0]
        actual = zlib.crc32(data[offset + 4:offset + 8 + length]) & 0xffffffff
        _require(stored == actual, f"{name}: invalid PNG chunk CRC")
        if first:
            _require(tag == b"IHDR" and length == 13,
                     f"{name}: PNG IHDR missing or malformed")
            width, height = struct.unpack_from(">II", payload)
            _require(0 < width <= 16384 and 0 < height <= 16384,
                     f"{name}: implausible PNG dimensions")
            dimensions = width, height
            first = False
        else:
            _require(tag != b"IHDR", f"{name}: duplicate PNG header")
        if tag == b"IDAT":
            idat_found = True
        if tag == b"IEND":
            _require(length == 0 and end == len(data),
                     f"{name}: malformed IEND or trailing PNG content")
            finished = True
            break
        offset = end
    _require(finished and idat_found and dimensions is not None,
             f"{name}: incomplete PNG image")
    return dimensions


def verify_recorded_gui_gallery(root: Path) -> dict:
    """Fail closed on missing, changed or substituted archive screenshots."""
    root = Path(root)
    gallery = root / GALLERY
    manifest_path = root / MANIFEST
    _require(gallery.is_dir() and not gallery.is_symlink(),
             "Real GUI screenshot directory is missing or symlinked")
    _require(manifest_path.is_file() and not manifest_path.is_symlink(),
             "Recorded capture manifest is missing or symlinked")
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8"),
        object_pairs_hook=_unique_json_pairs,
    )
    _require(isinstance(manifest, dict), "Capture manifest must be an object")
    _require(manifest.get("source_iteration") == "100"
             and manifest.get("selected_iteration_solver_converged") is False
             and manifest.get("engineering_release") == "HOLD"
             and manifest.get("physical_particle_validation") is False,
             "Original nonconverged capture evidence must remain engineering HOLD")
    _require(manifest.get("gui_callback_errors") == [],
             "The archived GUI capture recorded callback errors")
    source = manifest.get("source_provenance")
    _require(isinstance(source, dict), "Capture source provenance is missing")
    for key in ("manifest_sha256", "run_receipt_sha256", "project_source_sha256"):
        val = source.get(key)
        _require(type(val) is str and SHA256.fullmatch(val) is not None,
                 f"Invalid source provenance {key}")

    images = manifest.get("images")
    _require(isinstance(images, list) and len(images) == len(EXPECTED_NAMES),
             "Capture manifest must describe exactly 17 images")
    names = [entry.get("file") if isinstance(entry, dict) else None
             for entry in images]
    _require(sorted(names, key=str) == sorted(EXPECTED_NAMES),
             "Capture filenames missing, duplicated or altered")
    present = {p.name for p in gallery.iterdir() if p.suffix.lower() == ".png"}
    _require(present == set(EXPECTED_NAMES),
             "Gallery PNG files do not exactly match the source manifest")
    recorded = defaultdict(list)
    for image in images:
        name = image["file"]
        path = gallery / name
        _require(path.is_file() and not path.is_symlink(),
                 f"{name}: screenshot is absent or symlinked")
        _require(image.get("kind") in (
            "actual_Tk_window_pixels", "actual_VTK_render_window_framebuffer"),
            f"{name}: unrecognized image capture provenance")
        expected_sha = image.get("sha256")
        _require(type(expected_sha) is str and SHA256.fullmatch(expected_sha) is not None,
                 f"{name}: invalid source SHA-256")
        data = path.read_bytes()
        _require(0 < len(data) <= 32 * 1024 * 1024,
                 f"{name}: invalid or excessive image file size")
        actual_sha = hashlib.sha256(data).hexdigest()
        _require(actual_sha == expected_sha,
                 f"{name}: bytes differ from genuine recorded capture")
        dimensions = _png_dimensions(data, name)
        if "width" in image or "height" in image:
            _require(type(image.get("width")) is int
                     and type(image.get("height")) is int
                     and dimensions == (image["width"], image["height"]),
                     f"{name}: actual PNG dimensions disagree with capture metadata")
        recorded[actual_sha].append(name)

    duplicates = sorted(tuple(sorted(items)) for items in recorded.values()
                        if len(items) > 1)
    _require(duplicates == [EXPECTED_DUPLICATE],
             "Unexpected duplicated screenshot pixels or missing archived duplicate")

    gallery_readme_path = gallery / "README.md"
    root_readme_path = root / "README.md"
    _require(gallery_readme_path.is_file() and root_readme_path.is_file(),
             "Gallery or top-level README is missing")
    gallery_readme = gallery_readme_path.read_text(encoding="utf-8")
    root_readme = root_readme_path.read_text(encoding="utf-8")
    embeds = re.findall(r"!\[[^\]]*\]\(([^)\s]+\.png)\)", gallery_readme)
    _require(len(embeds) == 17 and set(embeds) == set(EXPECTED_NAMES),
             "Full GUI gallery must visibly embed each of the 17 PNGs once")
    _require("ENGINEERING" in gallery_readme.upper()
             and "HOLD" in gallery_readme.upper()
             and "16 distinct images" in gallery_readme,
             "Gallery must disclose HOLD and the duplicate image")
    _require("docs/real-gui-screenshots-20261021/README.md" in root_readme,
             "Main README must link the screenshot gallery")
    previews = re.findall(
        r"!\[[^\]]*\]\((docs/real-gui-screenshots-20261021/[^)\s]+\.png)\)",
        root_readme,
    )
    _require(len(previews) >= 4 and
             all(p.rsplit("/", 1)[1] in EXPECTED_NAMES for p in previews),
             "Top-level README must preview at least four authentic screenshots")
    return {"validated_png_files": len(images), "distinct_png_files": len(recorded),
            "recorded_source_iteration": manifest["source_iteration"],
            "engineering_release": "HOLD", "integrity": "PASS"}


def main() -> int:
    try:
        report = verify_recorded_gui_gallery(ROOT)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"FAIL recorded GUI archive: {exc}")
        return 1
    print("PASS recorded GUI archive: "
          f"{report['validated_png_files']} hashed PNGs, "
          f"{report['distinct_png_files']} distinct captures, "
          "README/gallery references and nonconverged-source provenance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
