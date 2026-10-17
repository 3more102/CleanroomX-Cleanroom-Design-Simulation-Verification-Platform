#!/usr/bin/env python3
"""Verify actual screenshot files against the capture manifest before publishing."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image

SCENES = frozenset({
    "gui-start-center",
    "gui-design-split-context",
    "gui-design-2d",
    "gui-design-3d",
    "gui-design-split",
    "gui-analysis-inputs",
    "gui-computed-fan-results",
    "gui-openfoam-workbench",
    "gui-openfoam-proofgraph-diagnostic",
})


def verify_gallery(directory: Path) -> int:
    manifest_path = directory / "screenshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "cleanroomx.gui-screenshot-capture.v1":
        raise ValueError("Screenshot manifest schema is missing or unsupported")
    if manifest.get("capture") != "real-tk-window-native-pixels":
        raise ValueError("Capture origin must identify the actual Tk window")
    if manifest.get("scientific_validation") != "NOT_ESTABLISHED":
        raise ValueError("Screenshots are not scientific validation")
    rows = manifest.get("images")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Empty screenshot capture manifest")
    target = manifest["target_window"]
    expected_size = (target["width_px"], target["height_px"])
    if expected_size[0] < 1440 or expected_size[1] < 900:
        raise ValueError("Capture resolution is below the documentation minimum")
    seen_names, seen_hashes, themes = set(), set(), set()
    combinations = set()

    for row in rows:
        name, scene, theme = row["filename"], row["scene"], row["theme"]
        if scene not in SCENES or theme not in ("light", "dark"):
            raise ValueError(f"Unknown screenshot scene or theme: {name}")
        expected_name = f"{scene}{'-dark' if theme == 'dark' else ''}.png"
        if name != expected_name or Path(name).name != name:
            raise ValueError(f"Unexpected filename or unsafe path: {name}")
        if name in seen_names or (scene, theme) in combinations:
            raise ValueError(f"Duplicate screenshot: {name}")
        seen_names.add(name)
        combinations.add((scene, theme))
        themes.add(theme)
        picture = directory / name
        data = picture.read_bytes()
        if len(data) != row["bytes"]:
            raise ValueError(f"Screenshot byte-count mismatch: {name}")
        digest = hashlib.sha256(data).hexdigest()
        if digest != row["sha256"]:
            raise ValueError(f"Screenshot SHA-256 mismatch: {name}")
        if digest in seen_hashes:
            raise ValueError(f"Two screenshots have identical content: {name}")
        seen_hashes.add(digest)
        with Image.open(picture) as img:
            if img.format != "PNG" or img.size != expected_size:
                raise ValueError(f"Screenshot resolution/format mismatch: {name}")
            if (row["width_px"], row["height_px"]) != img.size:
                raise ValueError(f"Manifest dimensions mismatch: {name}")
            # Pillow verify() must run immediately after opening, before load/convert.
            img.verify()
        with Image.open(picture) as img:
            extrema = img.convert("RGB").getextrema()
            if max(hi - lo for lo, hi in extrema) < 30:
                raise ValueError(f"Screenshot appears blank: {name}")
        expected_provenance = (
            "synthetic-sync-diagnostic"
            if scene == "gui-openfoam-proofgraph-diagnostic"
            else "computed-example-not-cfd"
            if scene == "gui-computed-fan-results"
            else "running-tk-application"
        )
        if row.get("provenance") != expected_provenance:
            raise ValueError(f"Data origin is missing or misleading: {name}")

    expected = {(scene, theme) for scene in SCENES for theme in themes}
    if combinations != expected:
        raise ValueError(f"Incomplete theme/scene coverage: {sorted(expected - combinations)}")
    print(f"Verified {len(rows)} genuine Tk captures ({', '.join(sorted(themes))})")
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path("docs/screenshots"),
        help="Directory containing screenshots and screenshot-manifest.json",
    )
    args = parser.parse_args()
    verify_gallery(args.input)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
