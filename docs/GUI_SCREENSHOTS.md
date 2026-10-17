# CleanroomX GUI screenshots

Use this guide to capture the **actual running CleanroomX application**. The capture utility opens the packaged demo and saves unedited screenshots of each main workspace and output panel. It does not construct substitute UI images or fabricate solver data.

## Capture the full GUI

Run from the repository root in a logged-in desktop session after installing the project and Pillow:

```powershell
python -m pip install -e .
python -m pip install Pillow
python scripts/capture_gui_screenshots.py
```

The screenshots and `capture-manifest.json` are written to `docs/gui_screenshots/`. The manifest records the capture time, source commit, application version, window dimensions, and capture status for each view.

The manual PDF includes these screenshots as landscape appendix pages when all 16 standard views exist and the manifest source commit matches the manual's documented preview commit. This prevents a partial or stale screenshot set from being presented as current.

| Screenshot file | GUI view captured |
| --- | --- |
| `start-center.png` | Start Center and project actions |
| `design-2d.png` | Floor plan and room editing |
| `design-3d.png` | Three-dimensional room view |
| `design-split.png` | Synchronized 2D and 3D design |
| `input-structured.png` | Structured project inputs |
| `input-json-editor.png` | Strict JSON input editor |
| `plot.png` | Analysis plot workspace in the packaged demo state |
| `proofgraph.png` | ProofGraph evidence explorer in the packaged demo state |
| `openfoam.png` | OpenFOAM case and evidence workbench |
| `output-problems.png` | Problems panel |
| `output-diagnostics.png` | Diagnostics panel |
| `output-verification.png` | Verification panel |
| `output-console.png` | Console panel |
| `output-evidence.png` | Evidence panel |
| `output-results.png` | Results panel |
| `output-report.png` | Report panel |

For a smaller desktop, choose an appropriate window size and allow extra time for rendering:

```powershell
python scripts/capture_gui_screenshots.py --width 1360 --height 820 --delay-seconds 2
```

The utility requires an interactive desktop display. It cannot capture screenshots from a headless shell. Pillow is used only for this optional documentation task and is not required to run CleanroomX.

## OpenFOAM time-series dialog

The packaged demo does not contain solver result data, so the regular capture set does not open or invent a time-series chart. To add a screenshot based on a real, existing result store, run:

```powershell
python scripts/capture_gui_screenshots.py --timeseries-result-directory "C:\path\to\cleanroomx-results"
```

The utility reads the result store through CleanroomX's hash-checking path and captures the displayed case, field, time labels, means, units, digest, and validation state. It does not alter the result store or generate substitute samples. Keep the visible scientific-validation limitation in the frame. The optional screenshot is included in the manual appendix when the 16 standard screenshots are also present and the manifest commit matches.

## Review before publishing

- Check that no personal project path, username, or unrelated desktop content is visible. The Start Center can contain local recent-project entries.
- Confirm the window title, selected workspace, status labels, and any validation limits are legible at native image size.
- Keep the images with their capture manifest and source commit.
- Do not add synthetic results or crop away labels that explain an integrity or validation limitation.
- Re-capture after major GUI layout changes rather than editing old images to resemble the current interface.
