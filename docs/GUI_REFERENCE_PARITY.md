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

## Visual refinement

The Studio now uses a restrained teal/navy palette, flat command styling,
segmented 2D/3D/Split controls and native vector branding. Four rounded metric
cards retain live model values; their icons are drawn with Canvas primitives.
The floating room navigator and detail cards share spacing and corner treatment.
Room dimensions have a clearer hierarchy, and the device breakdown uses labeled
icons alongside the actual per-room counts.

The camera dock highlights its actual preset. Hovering an action changes its
background and cursor, and the selected volume has a soft outline. Categorical
room walls have subtle face shading; engineering-overlay wall colors are kept
unchanged. None of these presentation effects modifies room geometry or invents
solver data.

**Edit** on a room card opens the actual property Inspector. When a device is
selected, Edit, Focus and Isolate resolve its assigned room. The desktop checks
exercise these actions, hover feedback, selected-camera state and live metric
text in addition to the existing selection/edit/save/reload workflows.

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

Desktop CI requires every selected case to run. If native Windows Tcl startup
fails before a test executes, that case gets one isolated-process retry. An
assertion failure or a further skip fails the job. The original JUnit reports,
isolated retry reports and a coverage receipt are retained together.

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
- Inline room cards scale to the available viewport height. The optional XYZ
  widget appears when it fits below them; shorter views keep the primary room
  actions visible. Screenshot capture waits for the final native repaint.

## Interactive equipment mini-map

The floating Room Navigator now draws **real equipment and opening coordinates** over the fitted miniature floor plan. Circular markers represent air devices, diamonds represent openings and squares represent other devices. Selecting a marker uses the existing shared device-selection path, so the 3D scene and selected-room context respond together. A selected device receives a ring, and Up/Down navigation advances relative to its assigned room. Off-plan markers are omitted from the tiny navigator to avoid obscuring the room list; these items remain accessible from the actual 2D/3D views and Find. All markers are derived from stored design geometry, **not** solver-computed fields.

Navigator rows also show live per-room device totals alongside the geometric floor area, so edits and reassignments can be checked without opening the Inspector.

## Selected-device inspector

Selecting an FFU, supply/return device, door, transfer opening, or other placed device now changes the right-hand lower Studio card from an aggregate count into a **Selected Device** readout: stored device name, type, room assignment, global X/Y position and Z above the design floor. Its **Inspect** action opens the actual editable Inspector and preserves the device selection. The original Selected Room panel and its Focus/Isolate controls continue to resolve the device's associated room. All values are geometry and configured inputs, not CFD outputs; empty/unknown selections are handled without inventing values.

The navigator footer is also a live hover hint: moving the pointer over a room or device shows its actual configured name and a geometry/type descriptor. Hover is presentation-only and does not modify the selected object or stored project. The pointer changes to a hand only over selectable geometry.

Selected Device also has a **Focus** camera action. It fits the actual selected equipment geometry in the 3D viewport while preserving device selection, unlike the existing room-focused camera action. The adjacent Inspect action opens editable properties.

## View-only equipment layers

Open **Display** in Design Studio to toggle **3D + navigator: Air devices**, **Openings** or **Other equipment** independently. The actual 3D and mini-map device glyphs are shown or hidden together. The room solids, navigation list, editable project/device objects and configured simulation inputs are not changed or deleted. Existing selection is preserved when its visual layer is hidden; toggling it back on restores its glyph. The footer lists enabled device layers, and the selected-device Inspector still shows canonical design facts even when the layer is off. Layer visibility is intentionally per-session UI state rather than an engineering input or a claim about solver visibility.

## Type-specific 3D equipment symbols

The 3D scene now distinguishes model device types with native Tk vectors: an FFU has a three-blade fan icon, supply has a downward arrow in a square, return/exhaust an upward arrow in a square, and other equipment a diamond icon. A selected device has a visible circular halo. These glyphs retain actual model selection hit tags and do not alter coordinates, volume, physical airflow, or simulated results.

The upper-left **Room Composition** header now includes one-click, dynamically counted AIR / OPEN / OTHER category chips. Clicking a chip toggles the matching Display-menu setting in both 3D and the mini-map; disabled chips visually deselect, and the room/device data remain unchanged. Controls hide on compact view heights rather than colliding with room geometry.

## Live engineering device schedule

The **Device schedule** button in the Design Studio toolbar and 3D header opens a real Tk equipment browser. It lists all canonical placed devices with name, type, assigned room, design X/Y and height above the floor, and stable device IDs. Search, room and category filters operate on the stored layout even when the 3D display layer is hidden. Select synchronizes shared spatial selection; Focus reveals a hidden category if needed and fits actual 3D equipment; Inspect opens the editable property panel. Device schedule updates after model redraws and shows current filtered versus total counts. **Export visible CSV** writes exactly the filtered rows and has spreadsheet-formula injection protections for imported textual names. No schedule field should be read as an OpenFOAM result or as measured airflow.
