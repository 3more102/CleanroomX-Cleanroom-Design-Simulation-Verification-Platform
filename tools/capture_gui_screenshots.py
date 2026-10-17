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


# Keep engineering-data provenance distinct from screenshot rendering.
SCENES = {
    "gui-start-center": "Desktop start center; bundled demonstration project",
    "gui-design-split-context": "2D/3D workspace with the surrounding engineering controls",
    "gui-design-2d": "2D plan view of the bundled demonstration model",
    "gui-design-3d": "3D view of the bundled demonstration model",
    "gui-design-split": "Synchronized 2D and 3D design views",
    "gui-analysis-inputs": "Editable input view for the bundled fan analysis",
    "gui-computed-fan-results": "Numerically computed fan/system example, not CFD",
    "gui-openfoam-workbench": "OpenFOAM workbench interface; no solver run implied",
    "gui-openfoam-proofgraph-diagnostic":
        "Synthetic OpenFOAM synchronization fixture; scientific validation BLOCKED",
}


def _window_size(value: str) -> tuple[int, int]:
    try:
        parts = value.lower().split("x")
        if len(parts) != 2:
            raise ValueError
        width, height = (int(part) for part in parts)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected WIDTHxHEIGHT (e.g. 1920x1080)") from exc
    if width < 1440 or height < 900 or width > 7680 or height > 4320:
        raise argparse.ArgumentTypeError("Window must be between 1440x900 and 7680x4320")
    return width, height


def _capture(
    root: tk.Tk,
    destination: Path,
    scene: str,
    theme: str,
) -> dict[str, object]:
    root.update_idletasks()
    root.update()
    time.sleep(0.25)
    root.update()
    x, y = root.winfo_rootx(), root.winfo_rooty()
    width, height = root.winfo_width(), root.winfo_height()
    if x < 0 or y < 0 or width < 1440 or height < 900:
        raise RuntimeError(f"Window is not correctly framed: {x},{y} {width}x{height}")
    if x + width > root.winfo_screenwidth() or y + height > root.winfo_screenheight():
        raise RuntimeError("Captured application would extend beyond the virtual display")
    # Grab the real Tk window in its native pixel dimensions; do not enlarge
    # small captures, synthesize results, sharpen labels or remove UI elements.
    image = ImageGrab.grab(bbox=(x, y, x + width, y + height)).convert("RGB")
    if image.size != (width, height):
        raise RuntimeError(f"Unexpected capture dimensions for {scene}: {image.size}")
    if max(high - low for low, high in image.getextrema()) < 30:
        raise RuntimeError(f"Likely blank or unreadable desktop capture: {scene}")
    filename = f"{scene}{'-dark' if theme == 'dark' else ''}.png"
    location = destination / filename
    image.save(location, format="PNG", optimize=True)
    digest = _sha256(location.read_bytes())
    print(f"Captured {filename} ({width}x{height}) SHA-256 {digest[:12]}")
    return {
        "filename": filename,
        "scene": scene,
        "theme": theme,
        "width_px": width,
        "height_px": height,
        "sha256": digest,
        "bytes": location.stat().st_size,
        "description": SCENES[scene],
        "provenance": (
            "synthetic-sync-diagnostic"
            if scene == "gui-openfoam-proofgraph-diagnostic"
            else "computed-example-not-cfd"
            if scene == "gui-computed-fan-results"
            else "running-tk-application"
        ),
    }


def _select_tab(app: CleanroomXApp, label: str) -> None:
    for tab_id in app.notebook.tabs():
        if app.notebook.tab(tab_id, "text") == label:
            app.notebook.select(tab_id)
            app.root.update_idletasks()
            app.root.update()
            return
    raise RuntimeError(f"CleanroomX GUI tab was not found: {label}")


def _capture_theme(
    app: CleanroomXApp,
    output: Path,
    theme: str,
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    app.set_focus_workspace(False)
    app.set_theme(theme, persist=False)

    def snap(scene: str) -> None:
        records.append(_capture(app.root, output, scene, theme))

    _select_tab(app, "Start")
    snap("gui-start-center")

    app.spatial_workspace.set_workspace_mode("split")
    _select_tab(app, "Design")
    snap("gui-design-split-context")

    app.set_focus_workspace(True)
    for mode, scene in (
        ("2d", "gui-design-2d"),
        ("3d", "gui-design-3d"),
        ("split", "gui-design-split"),
    ):
        app.spatial_workspace.set_workspace_mode(mode)
        _select_tab(app, "Design")
        snap(scene)

    app.set_focus_workspace(False)
    app.select_demo_plot_analysis()
    _select_tab(app, "Input")
    snap("gui-analysis-inputs")

    # This is a real CleanroomX numerical calculation, not an OpenFOAM result.
    app.smoke_run_active()
    _select_tab(app, "Plot")
    snap("gui-computed-fan-results")

    app.openfoam_workspace._workflow_canvas.yview_moveto(0)
    _select_tab(app, "OpenFOAM")
    snap("gui-openfoam-workbench")

    _select_tab(app, "ProofGraph")
    snap("gui-openfoam-proofgraph-diagnostic")
    return records


def capture(
    output: Path,
    *,
    size: tuple[int, int] = (1920, 1080),
    themes: tuple[str, ...] = ("light", "dark"),
    scaling: float = 1.15,
) -> dict[str, object]:
    if not themes or len(set(themes)) != len(themes):
        raise ValueError("Themes must be distinct and non-empty")
    if any(theme not in ("light", "dark") for theme in themes):
        raise ValueError("Only light and dark themes are supported")
    if not 0.8 <= scaling <= 2.0:
        raise ValueError("Tk scaling must be between 0.8 and 2.0")
    width, height = size
    if _window_size(f"{width}x{height}") != size:
        raise ValueError("Invalid capture size")

    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="cleanroomx-gui-capture-") as temp:
        temporary_root = Path(temp)
        proofgraph_root = temporary_root / "openfoam-results"
        _write_synthetic_openfoam_store(proofgraph_root)
        proofgraph = proofgraph_from_openfoam_sync_results(
            proofgraph_root, SIMULATION_ID
        )
        root = tk.Tk()
        try:
            if (
                root.winfo_screenwidth() < width
                or root.winfo_screenheight() < height
            ):
                raise RuntimeError(
                    f"Virtual display {root.winfo_screenwidth()}x"
                    f"{root.winfo_screenheight()} cannot fit {width}x{height}; "
                    "increase Xvfb -screen size or choose a smaller --size"
                )
            root.tk.call("tk", "scaling", scaling)
            app = CleanroomXApp(
                root,
                autosave_interval_seconds=0,
                ui_state_path=temporary_root / "gui-layout.json",
            )
            root.geometry(f"{width}x{height}+0+0")
            app.load_project_path(bundled_demo_project_path())
            app.proofgraph_viewer.set_documents([proofgraph.to_dict()])
            root.update_idletasks()
            root.update()
            screenshots = []
            for theme in themes:
                screenshots.extend(_capture_theme(app, output, theme))
        finally:
            root.destroy()

    if len({row["sha256"] for row in screenshots}) != len(screenshots):
        raise RuntimeError("Two screenshots are byte-identical; inspect tabs before publishing")
    manifest = {
        "schema": "cleanroomx.gui-screenshot-capture.v1",
        "capture": "real-tk-window-native-pixels",
        "source_project": "bundled-demo-project",
        "target_window": {"width_px": width, "height_px": height},
        "tk_scaling": scaling,
        "scientific_validation": "NOT_ESTABLISHED",
        "notes": [
            "These are genuine desktop GUI screenshots, not generated mockups.",
            "The fan operating-point plot uses the real numerical example, not CFD.",
            "The ProofGraph view uses synthetic synchronization metadata; scientific validation remains BLOCKED.",
            "No screenshots represent CFD convergence or measured cleanroom performance.",
        ],
        "images": screenshots,
    }
    (output / "screenshot-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Verified {len(screenshots)} real GUI captures across {len(themes)} themes")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("docs/screenshots"),
        help="Output directory (default: docs/screenshots)",
    )
    parser.add_argument(
        "--size", type=_window_size, default=(1920, 1080),
        help="Real application window size: WIDTHxHEIGHT (default: 1920x1080)",
    )
    parser.add_argument(
        "--themes", nargs="+", choices=("light", "dark"),
        default=["light", "dark"],
        help="Capture one or both presentation themes",
    )
    parser.add_argument(
        "--tk-scaling", type=float, default=1.15,
        help="Tk UI scaling for legibility (default: 1.15)",
    )
    args = parser.parse_args()
    capture(
        args.output, size=args.size, themes=tuple(args.themes),
        scaling=args.tk_scaling,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
