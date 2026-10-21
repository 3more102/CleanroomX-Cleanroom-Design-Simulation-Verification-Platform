"""Offline fixture tests for 17-image GUI archive provenance checks.

Fixtures are synthetic PNG byte sequences, NOT CleanroomX CFD evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_recorded_gui_gallery import (  # noqa: E402
    EXPECTED_NAMES, verify_recorded_gui_gallery,
)


def _chunk(tag, payload):
    return (struct.pack(">I", len(payload)) + tag + payload +
            struct.pack(">I", zlib.crc32(tag + payload) & 0xffffffff))


def _tiny_png(rgb):
    header = struct.pack(">IIBBBBB", 2, 1, 8, 2, 0, 0, 0)
    raw = b"\x00" + bytes(rgb) * 2
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) +
            _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b""))


class RecordedGalleryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.gallery = self.root / "docs/real-gui-screenshots-20261021"
        self.gallery.mkdir(parents=True)
        self.manifest_path = (self.root /
            "reports/engineering-session-20261021/capture-manifest.json")
        self.manifest_path.parent.mkdir(parents=True)
        self.manifest = {
            "source_iteration": "100",
            "selected_iteration_solver_converged": False,
            "engineering_release": "HOLD",
            "physical_particle_validation": False,
            "gui_callback_errors": [],
            "source_provenance": {
                "manifest_sha256": "a" * 64,
                "run_receipt_sha256": "b" * 64,
                "project_source_sha256": "c" * 64,
            },
            "images": [],
        }
        embeds = []
        for index, name in enumerate(EXPECTED_NAMES):
            key = 4 if index == 7 else index
            png = _tiny_png(((key * 7) % 256, (key * 13) % 256, (key * 19) % 256))
            (self.gallery / name).write_bytes(png)
            self.manifest["images"].append({
                "file": name, "sha256": hashlib.sha256(png).hexdigest(),
                "kind": "actual_Tk_window_pixels",
                "width": 2, "height": 1,
            })
            embeds.append(f"![screen]({name})")
        (self.gallery / "README.md").write_text(
            "# Actual GUI archive — ENGINEERING HOLD\n"
            "17 screenshots, 16 distinct images\n" + "\n".join(embeds),
            encoding="utf-8",
        )
        (self.root / "README.md").write_text(
            "[All screenshots](docs/real-gui-screenshots-20261021/README.md)\n" +
            "\n".join(
                f"![preview](docs/real-gui-screenshots-20261021/{name})"
                for name in EXPECTED_NAMES[:4]),
            encoding="utf-8",
        )
        self.save_manifest()

    def save_manifest(self):
        self.manifest_path.write_text(
            json.dumps(self.manifest, indent=2) + "\n", encoding="utf-8")

    def test_authentic_shape_and_declared_archive_duplicate(self):
        result = verify_recorded_gui_gallery(self.root)
        self.assertEqual(result["validated_png_files"], 17)
        self.assertEqual(result["distinct_png_files"], 16)
        self.assertEqual(result["engineering_release"], "HOLD")

    def test_corrupted_source_image_rejected(self):
        p = self.gallery / EXPECTED_NAMES[0]
        p.write_bytes(p.read_bytes() + b"x")
        with self.assertRaisesRegex(ValueError, "differ from genuine"):
            verify_recorded_gui_gallery(self.root)

    def test_missing_image_rejected(self):
        (self.gallery / EXPECTED_NAMES[2]).unlink()
        with self.assertRaisesRegex(ValueError, "exactly match"):
            verify_recorded_gui_gallery(self.root)

    def test_unexpected_png_rejected(self):
        (self.gallery / "extra.png").write_bytes(_tiny_png((10, 20, 30)))
        with self.assertRaisesRegex(ValueError, "exactly match"):
            verify_recorded_gui_gallery(self.root)

    def test_mutated_gallery_embedding_rejected(self):
        path = self.gallery / "README.md"
        path.write_text(path.read_text().replace(
            f"![screen]({EXPECTED_NAMES[3]})", "Screenshot 04"),
            encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "visibly embed"):
            verify_recorded_gui_gallery(self.root)

    def test_forged_convergence_and_release_rejected(self):
        self.manifest["selected_iteration_solver_converged"] = True
        self.manifest["engineering_release"] = "PASS"
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "HOLD"):
            verify_recorded_gui_gallery(self.root)

    def test_unexpected_duplicate_capture_rejected(self):
        original = (self.gallery / EXPECTED_NAMES[0]).read_bytes()
        other = self.gallery / EXPECTED_NAMES[1]
        other.write_bytes(original)
        self.manifest["images"][1]["sha256"] = hashlib.sha256(original).hexdigest()
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "duplicated"):
            verify_recorded_gui_gallery(self.root)

    def test_png_crc_rejected_even_after_rehash(self):
        target = self.gallery / EXPECTED_NAMES[1]
        data = bytearray(target.read_bytes())
        data[29] ^= 1  # Corrupt IHDR CRC without corrupting the signature.
        target.write_bytes(data)
        self.manifest["images"][1]["sha256"] = hashlib.sha256(data).hexdigest()
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "CRC"):
            verify_recorded_gui_gallery(self.root)

    def test_forged_dimensions_rejected(self):
        self.manifest["images"][0]["width"] = 3
        self.save_manifest()
        with self.assertRaisesRegex(ValueError, "dimensions"):
            verify_recorded_gui_gallery(self.root)

    def test_symlinked_image_rejected_if_supported(self):
        img = self.gallery / EXPECTED_NAMES[1]
        temp = self.gallery / "hold.bin"
        temp.write_bytes(img.read_bytes())
        img.unlink()
        try:
            img.symlink_to(temp)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks unavailable on this system")
        with self.assertRaisesRegex(ValueError, "symlinked"):
            verify_recorded_gui_gallery(self.root)

    def test_manifest_duplicate_json_key_rejected(self):
        content = self.manifest_path.read_text(encoding="utf-8")
        self.manifest_path.write_text(
            content.replace('"source_iteration": "100",',
                            '"source_iteration": "100",\n"source_iteration": "100",',
                            1),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            verify_recorded_gui_gallery(self.root)

    def test_missing_root_preview_rejected(self):
        (self.root / "README.md").write_text(
            "[Gallery](docs/real-gui-screenshots-20261021/README.md)",
            encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "preview"):
            verify_recorded_gui_gallery(self.root)


if __name__ == "__main__":
    unittest.main()
