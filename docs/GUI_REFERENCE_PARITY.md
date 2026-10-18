# CleanroomX Design Studio — Reference Parity

## Scope and verification state

Reference: supplied Design Studio screenshot, dark navy/cyan three-room demo.
Implementation branch: `chatgpt/design-studio-parity-20261019`.
Source baseline: `main` at `cf5506ffc5793313e023118209faafefc17e73b7`.

**Implemented in source, not yet visually accepted:** four model-derived live
metrics; 3D-viewport Room Navigator with live miniature 2D geometry, floor-area
labels and synchronized room selection; selected-room summary; device category
counts; Focus Room, Isolate and Show All wired to existing workspace operations.

The existing Tkinter Canvas 2D/3D renderer, project persistence, selection,
camera controls, engineering analysis tools and OpenFOAM backend remain in place.
No new CFD or solver-computed result is implied by these changes.

### Acceptance matrix

| Criterion | Evidence | Status |
|---|---|---|
| Demo rooms 3 / 62 m² / 186 m³ / 10 devices | `src/cleanroomx/demo/gui_demo.cleanroomx.json`, snapshot math and focused tests | Source implemented; tests pending CI |
| Live cards change with edits | `redraw() -> _update_studio_panels()`; mutation tests | Source implemented; tests pending CI |
| Room Navigator shows actual rooms | `navigator_room_rectangles`, `_draw_room_navigator` | Source implemented; visual check pending |
| Navigator → 3D selection & inspector | `_on_navigator_click -> select_item(..., notify=True)` | Source implemented; GUI check pending |
| 3D/2D → Navigator selection | Existing `select_item` + `redraw` path | Source implemented; GUI check pending |
| Selected room details and pressure provenance | `design_studio_snapshot`, explicit *design pressure setpoint* label | Source implemented; tests pending CI |
| Focus / Isolate / Show All | Existing verified operations reused | Source wired; GUI check pending |
| Resize behavior | Existing Panedwindow plus viewport overlay | Unverified; inspect at 1920×1080 and narrow widths |
| Visual matching to reference | Genuine baseline and updated screenshots required | **Not verified** |
| OpenFOAM execution and fields | Existing code unchanged | **Not newly verified** |
| Full regression | CI / local `pytest` required | **Not run in this environment** |

### Evidence and percentages

No percentage is asserted because reference screenshot comparison and application
execution have not been completed in the Windows desktop environment. Visual,
functional, interaction, synchronization, OpenFOAM and automation denominators
must each be defined in a reviewed checklist before claiming 100%.

### Reproduce and validate on the Windows workstation

Run from the repository root on this implementation branch:

```powershell
python -m pip install -e ".[dev]"
python -m pytest tests/test_design_studio_parity.py -q
python -m pytest tests -q
cleanroomx-gui --demo
```

Set the application to 1920×1080 and capture **real** GUI screenshots. Compare
the original Design Studio reference for layout, 3D room geometry, navigator,
colors, four metrics and the selected-room/placed-devices panels. Exercise
room add/edit/delete, device add/edit/delete, 2D/3D picking, room focus/isolation,
undo/redo, save/reload, window resizing and verified CFD state.

### Known gaps / next priorities

1. Capture a real pre-change baseline from the original checkout and a real
   post-change image from this branch; no screenshots have been fabricated.
2. Review sidebar scrolling, small-screen behavior and room navigator overlay
   placement on the running application.
3. Compare actual colors, spacing, labels, fonts and transparency to reference.
4. Run focused/full automated tests and record **actual** pass/fail/skip counts.
5. Trace OpenFOAM solver provenance independently before showing completion
   percentages or populated CFD plots.

Report folder `reports/gui_reference_parity/` is reserved for real execution
receipts and genuine screenshots, not inferred metrics.
