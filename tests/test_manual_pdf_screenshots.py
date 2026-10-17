from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import pytest

pytest.importorskip("reportlab")

from scripts import render_solution_manual_pdf as manual_pdf


def _png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    row = b"\x00" + (b"\xC8\xD8\xE8\xFF" * width)
    raw = row * height
    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(
        b"IDAT", zlib.compress(raw)
    ) + chunk(b"IEND", b"")


def _capture_set(source: Path, commit: str = "0193925" + "a" * 33) -> None:
    screenshot_dir = source.parent / "gui_screenshots"
    screenshot_dir.mkdir(parents=True)
    png = _png(700, 500)
    captures = []
    for filename in manual_pdf.GUI_SCREENSHOT_FILES:
        (screenshot_dir / filename).write_bytes(png)
        captures.append({"file": filename, "dimensions_px": [700, 500]})
    (screenshot_dir / "capture-manifest.json").write_text(
        json.dumps({
            "source_commit": commit,
            "errors": [],
            "captures": captures,
        }),
        encoding="utf-8",
    )


def test_manual_without_capture_manifest_does_not_add_fake_images(tmp_path: Path) -> None:
    source = tmp_path / "manual.md"

    assert manual_pdf._load_gui_screenshot_records(source, "branch @ 0193925") is None


def test_manual_embeds_all_commit_matched_gui_screenshots(tmp_path: Path) -> None:
    source = tmp_path / "manual.md"
    _capture_set(source)
    story = []

    manual_pdf.add_gui_screenshot_gallery(
        story,
        source,
        "gui/openfoam-timeseries-workbench-20261017 @ 0193925 (0.103.0.dev0)",
    )

    screenshots = [item for item in story if isinstance(item, manual_pdf.PDFImage)]
    assert len(screenshots) == len(manual_pdf.GUI_SCREENSHOT_FILES)
    assert any(isinstance(item, manual_pdf.NextPageTemplate) for item in story)


def test_manual_rejects_stale_screenshot_commit(tmp_path: Path) -> None:
    source = tmp_path / "manual.md"
    _capture_set(source, commit="deadbee" + "a" * 33)

    with pytest.raises(ValueError, match="different source commit"):
        manual_pdf._load_gui_screenshot_records(source, "branch @ 0193925")


def test_manual_rejects_incomplete_screenshot_set(tmp_path: Path) -> None:
    source = tmp_path / "manual.md"
    _capture_set(source)
    manifest_path = source.parent / "gui_screenshots" / "capture-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["captures"].pop()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="screenshot set is incomplete"):
        manual_pdf._load_gui_screenshot_records(source, "branch @ 0193925")
