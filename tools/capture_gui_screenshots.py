#!/usr/bin/env python3
"""Capture actual CleanroomX Tk windows for the user and GUI manual.

Run under Xvfb on CI. The OpenFOAM ProofGraph image uses a clearly documented,
synthetic synchronization fixture to show the viewer's diagnostic-only states.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time

import tkinter as tk
from PIL import ImageGrab

from cleanroomx.cfd_proofgraph import proofgraph_from_openfoam_sync_results
from cleanroomx.gui import CleanroomXApp, bundled_demo_project_path


SIMULATION_ID = "ui-screenshot-demo"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_synthetic_openfoam_store(root: Path) -> None:
    """Create a tiny, explicitly synthetic sync record for the ProofGraph view."""
    case = root / SIMULATION_ID / "configuration_1"
    output = case / "results" / "time_100"
    vtk_path = output / "VTK" / "field.vtk"
    log_path = output / "foamToVTK.log"
    vtk_path.parent.mkdir(parents=True)
    vtk_bytes = b"# vtk DataFile Version 3.0\nsynthetic screenshot fixture\n"
    log_bytes = b"OpenFOAM Foundation v10\nTime: 100\nEnd\n"
    vtk_path.write_bytes(vtk_bytes)
    log_path.write_bytes(log_bytes)

    source_fields = {
        "U": {
            "path": "100/U",
            "sha256": _sha256(b"synthetic source field metadata only"),
            "size_bytes": 48,
        }
    }
    fingerprint = _sha256(
        json.dumps(source_fields, sort_keys=True, separators=(",", ":")).encode()
    )
    record = {
        "time_name": "100",
        "selected_times": ["100"],
        "input_fingerprint_sha256": fingerprint,
        "source_fields": source_fields,
        "fields": {"U": {"units": "m/s"}},
        "cell_count": 12,
        "imported_field_summary": {"U": {"status": "PASS"}},
        "native_vtk_parity": {"U": {"status": "PASS"}},
        "cleanroomx_analysis_import": {"status": "PASS"},
        "surface_phi_parity": None,
        "assets": [
            {
                "path": vtk_path.relative_to(case).as_posix(),
                "sha256": _sha256(vtk_bytes),
                "size_bytes": len(vtk_bytes),
            },
            {
                "path": log_path.relative_to(case).as_posix(),
                "sha256": _sha256(log_bytes),
                "size_bytes": len(log_bytes),
            },
        ],
        "foamToVTK_log_sha256": _sha256(log_bytes),
        "import_status": "PASS_DIAGNOSTIC_ONLY",
        "scientific_validation": "BLOCKED",
    }
    receipt_bytes = (
        json.dumps(
            {
                "schema_version": "cleanroomx.openfoam-result-sync.v2",
                "simulation_id": SIMULATION_ID,
                "case_id": "configuration_1",
                "configuration_hash": "a" * 64,
                "time_name": "100",
                "record": record,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    ).encode()
    receipt_path = output / "receipt.json"
    receipt_path.write_bytes(receipt_bytes)
    record["receipt"] = {
        "path": receipt_path.relative_to(case).as_posix(),
        "sha256": _sha256(receipt_bytes),
    }
    manifest = {
        "schema_version": "cleanroomx.openfoam-result-sync.v2",
        "interpretation": "solver_output_import_and_integrity_only",
        "scientific_validation": "BLOCKED",
        "simulation_id": SIMULATION_ID,
        "case_id": "configuration_1",
        "configuration_hash": "a" * 64,
        "solver_release": "OpenFOAM Foundation v10",
        "solver_build": "synthetic-screenshot-fixture",
        "status": "results_synced",
        "solver_returncode": 0,
        "solver_log_status": "completed",
        "record_count": 1,
        "error_count": 0,
        "records": {"100": record},
        "errors": [],
    }
    (case / "sync_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _capture(root: tk.Tk, destination: Path, name: str) -> None:
    root.update_idletasks()
    root.update()
    time.sleep(0.2)
    x = root.winfo_rootx()
    y = root.winfo_rooty()
    width = root.winfo_width()
    height = root.winfo_height()
    if width < 1000 or height < 650:
        raise RuntimeError(f"GUI window is too small to capture: {width}x{height}")
    image = ImageGrab.grab(bbox=(x, y, x + width, y + height))
    image.save(destination / f"{name}.png", format="PNG")
    print(f"Captured {name}.png ({width}x{height})")


def _select_tab(app: CleanroomXApp, label: str) -> None:
    for tab_id in app.notebook.tabs():
        if app.notebook.tab(tab_id, "text") == label:
            app.notebook.select(tab_id)
            app.root.update_idletasks()
            app.root.update()
            return
    raise RuntimeError(f"CleanroomX GUI tab was not found: {label}")


def capture(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cleanroomx-gui-capture-") as temp:
        temporary_root = Path(temp)
        proofgraph_root = temporary_root / "openfoam-results"
        _write_synthetic_openfoam_store(proofgraph_root)
        proofgraph = proofgraph_from_openfoam_sync_results(
            proofgraph_root, SIMULATION_ID
        )

        root = tk.Tk()
        app = CleanroomXApp(
            root,
            autosave_interval_seconds=0,
            ui_state_path=temporary_root / "gui-layout.json",
        )
        try:
            root.geometry("1440x900+0+0")
            app.load_project_path(bundled_demo_project_path())
            root.update_idletasks()
            root.update()

            _select_tab(app, "Start")
            _capture(root, output, "gui-start-center")

            app.set_focus_workspace(True)
            app.spatial_workspace.set_workspace_mode("2d")
            _select_tab(app, "Design")
            _capture(root, output, "gui-design-2d")

            app.spatial_workspace.set_workspace_mode("3d")
            _select_tab(app, "Design")
            _capture(root, output, "gui-design-3d")

            app.spatial_workspace.set_workspace_mode("split")
            _select_tab(app, "Design")
            _capture(root, output, "gui-design-split")

            app.select_demo_plot_analysis()
            app.smoke_run_active()
            _select_tab(app, "Plot")
            _capture(root, output, "gui-computed-fan-results")

            app.openfoam_workspace._workflow_canvas.yview_moveto(0)
            _select_tab(app, "OpenFOAM")
            _capture(root, output, "gui-openfoam-workbench")

            app.proofgraph_viewer.set_documents([proofgraph.to_dict()])
            _select_tab(app, "ProofGraph")
            _capture(root, output, "gui-openfoam-proofgraph-diagnostic")
        finally:
            root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/screenshots"),
        help="Directory for captured PNG images (default: docs/screenshots)",
    )
    args = parser.parse_args()
    capture(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
