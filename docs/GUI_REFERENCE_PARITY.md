# CleanroomX Design Studio — reference implementation

The reference layout is implemented in the actual Tk desktop application.
The original 1536 × 960 reference is the visual target. The implementation uses
live projected room geometry and the canonical spatial layout; it does not
paint a screenshot over the application or substitute a generated mockup.

## Open the implemented workspace

```powershell
git fetch origin gui/design-studio-reference-parity-20261019
git switch gui/design-studio-reference-parity-20261019
git pull --ff-only
python -m pip install -e ".[dev]"
cleanroomx-gui --demo
```

`--demo` now opens the bundled project directly in the dark Design Studio.
For another project, use `cleanroomx-gui path/to/project.cleanroomx.json --studio`.
Use **More tools** to expose the application menu, editing controls and
engineering overlays. **Inspector** opens the scrollable property editor.
Selecting 2D or Split restores the normal editing chrome.

## Reference components and behavior

| Reference component | Implemented behavior |
| --- | --- |
| Navy/cyan application chrome | Dark theme with compact, reversible Studio presentation |
| Project and command bars | Existing New/Open/Save and project controls remain functional |
| Guided workflow | Highlights the actual stage; Design is selected while editing |
| Design Studio command row | Add room, add device/opening and room/device search |
| View controls | 2D, 3D, Split, Fit, Balance, Studio View and Inspector |
| Camera toolbar | View presets, projection selection, Reset and orbit/tilt buttons |
| Interior / section / display | Cutaway toggle, real elevation clipping and engineering overlays |
| Summary cards | Live room count, geometric area, geometric volume and placed-device count |
| Integrated room model | Camera-oriented cutaway walls, colored floors, selection outline and labeled rooms |
| Device visualization | Openings use their actual width, height and orientation; elevated device markers have drop lines |
| Pressure relationships | Arrows use the configured engineering relationships; no solver result is invented |
| Room Navigator | Scaled floorplan, numbered color key, selectable rows, scrolling and keyboard room navigation |
| Selected Room panel | Live classification, dimensions, area, volume, device count and pressure setpoint |
| Placed in This Room panel | Counts only devices assigned to the selected room |
| Focus / isolate / camera footer | Clickable Focus, Isolate/Restore, Top, Front, Iso and Fit controls |

The room palette is categorical identity coloring. Pressure coloring is available
from Display. A displayed **pressure setpoint** is configured project input,
not evidence of an OpenFOAM calculation.

The bundled demo computes 3 rooms, 62 m², 186 m³ and 10 devices/openings.
These values are not hardcoded in the dashboard. Room edits and device
assignment changes update the same model used by the scene and project file.

| Room | FFU | Supply | Return / exhaust | Other | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Process | 1 | 1 | 1 | 2 | 5 |
| Preparation | 0 | 1 | 1 | 1 | 3 |
| Ante / Airlock | 0 | 0 | 0 | 2 | 2 |

## Verification and evidence

The reference tests exercise real Tk widgets and events: navigator and scene
selection, Focus/Isolate/Restore, camera buttons, mouse orbit and zoom, F to
fit, interior visibility, section clipping, Inspector and More tools, room
editing, and Save As followed by reloading the actual project file.
Layout checks cover 1280 × 800, 1536 × 960 and 1920 × 1080 windows.

The full test results and exact source revision are recorded in
`reports/gui_reference_parity/verification.json`. Actual desktop captures and
SHA-256 receipts are stored alongside it. The capture script records hashes
of the imported renderer source files, the reference image and the PNG.

```bash
python -m pytest -q tests/test_design_studio_reference.py tests/test_gui_engineering_panels.py tests/test_gui_proofgraph.py tests/test_gui_proofgraph_integration.py
python -m pytest -q
python scripts/capture_design_studio.py --width 1536 --height 960 --output reports/gui_reference_parity/design_studio_1536x960.png
```

On headless Linux, run the GUI commands under a real X display such as Xvfb.
The CI workflow also runs desktop interaction tests on Windows. A Windows CI
result must be read from the current run; merely configuring the job is not
a pass. The user's installed Windows desktop has not been inspected here.

The Linux screenshots are visually reviewed against the supplied reference.
The layout and listed components are reproduced; no pixel-identical claim or
unmeasured visual-similarity percentage is made. Font rasterization and native
platform appearance can vary. This GUI change does not validate OpenFOAM
solver execution or merge itself into the default branch.

## Integration defects corrected during validation

- Selected-room device grouping previously showed project-wide counts.
- The Inspector could push editable geometry fields beyond a short window;
  the property editor now scrolls.
- Fit Selected now returns its documented success result without changing
  engineering geometry.
- ProofGraph selection rebuilt its own tree on each queued selection event,
  causing an event loop; selection echoes are now ignored.
- ProofGraph searches for an explicit node ID now anchor its immediate trace
  context instead of expanding copied provenance as additional direct hits.
- Startup panel splits are restored after native Tk maps the panes, keeping
  the editing canvas visible on smaller displays.
- Inspector entry focus is deferred until the panel can receive keyboard input.
  Windows tests activate their test window and compare restored client dimensions
  with the actual saved size, accounting for native window decorations.
- Saved window dimensions retain valid small-display client sizes instead of
  replacing them with defaults larger than the display.
