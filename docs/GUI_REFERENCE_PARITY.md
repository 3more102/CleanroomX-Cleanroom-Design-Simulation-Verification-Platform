# CleanroomX GUI reference parity — evidence and acceptance ledger

**Tracking date:** 2026-10-19  
**Change branch:** `feat/gui-reference-parity-navigator-20261019`  
**Parent implementation:** `feat/real-design-studio-20261018` (PR #1344)  
**Target application:** `cleanroomx-gui --demo`  

## Scope and current facts

The existing desktop is Tkinter, with model-backed 2D/3D canvas rendering in
`src/cleanroomx/spatial.py` and Design Studio chrome in
`src/cleanroomx/gui_design_studio.py`. The baseline PR implements summary
cards, an interactive floor-plan navigator, room details, focused/isolated
selection, and roofless 3D cutaway rendering. It is **not** a true RGBA
3D/mesh renderer. Wall openings are projected outlines rather than Boolean
solid cutouts. Do not claim pixel-for-pixel parity or CFD accuracy from GUI
source inspection.

## 2026-10-19 iteration

1. Fix mini-plan invalidation: redraw on `x_m`, `y_m`, `length_m`,
   `width_m`, identity, label, selection, and room ordering changes. The
   old redraw signature only checked room identity, name and area, so moving
   a room or changing its aspect ratio at constant area left the navigator
   stale.
2. Make the right panel say **Layout pressure (not CFD)** so values in
   the canonical layout cannot be mistaken for verified OpenFOAM outputs.
3. Add an explicit **Restore all rooms** control. Search now clears a
   visibility/isolation filter if the matching object would be hidden.
4. Add pure snapshot/signature tests and Tk widget regressions for
   redraw invalidation and restoration.
5. Parameterize genuine Tk screenshot capture. CI is configured to produce
   separate images at **1536 × 960** (reference aspect/size) and
   **1920 × 1080** (user-specified desktop acceptance size).

## Acceptance checklist

| Acceptance area | Evidence source | State on this iteration |
| --- | --- | --- |
| Application and bundled demo start | `tests/test_gui_design_studio.py`, CI | Pending branch CI |
| Live rooms / area / volume / device cards | `studio_snapshot`, Tk test | Implemented; pending branch CI |
| Room navigator tracks position and aspect ratio edits | `studio_nav_signature`, tests | Patch committed; pending branch CI |
| Selection synchronization with the 3D scene | existing Tk integration test | Implemented; pending branch CI |
| Focus, isolate, restore and Studio View | real spatial callbacks, Tk test | Patch committed; pending branch CI |
| Layout vs solver-result provenance | explicit inspector label | Patch committed; pending branch CI |
| 2D / 3D / Split / camera/persistence | existing spatial and project tests | No new claim; full regression required |
| Full OpenFOAM case/mesh/solver/result loop | real solver receipts and checks | Not verified in this GUI iteration |
| Screenshot visual parity | genuine images + human review against supplied reference | Not reviewed; **do not claim pass** |
| Full CI and severity review | current head workflows, issue inventory | Pending independent verification |

## Percentage policy — no invented numbers

Store **N/A (unverified)** until the stated denominator is audited:

- **Visual parity:** passed visual checkpoints / 12 (layout, header,
  workflow, four cards, viewport geometry, materials, overlays, navigator,
  inspector, responsive behavior, typography). Requires genuine reference
  comparison at the same resolution.
- **GUI functions:** passed working controls / controls enumerated from
  the running application, including error states and persistence.
- **3D interactions:** passed verified interactions / documented supported
  mouse and camera operations (orbit, pan, zoom, fit, presets, selection,
  focus, isolate, restore, view modes).
- **Room/device sync:** passed canonical mutation/selection scenarios /
  explicit cases covering create, edit, delete, move, resize, save/reload,
  selection, and orphan/error cases.
- **OpenFOAM:** passed verified source→case→mesh→solver→result→GUI
  evidence paths / independently enumerated applicable field/workflow cases.
  Feature presence is not counted as backend integration.
- **Automated verification:** passing mandatory scenarios / total applicable
  mandatory scenarios; report fail, error and skip separately.

Do **not** infer the denominators from rough feature counts or output
`100%` because screenshots or widgets exist.

## Verification commands

From an isolated worktree with Python 3.11+ and Tk installed:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_gui_design_studio.py tests/test_spatial_editing_gui.py
python -m pytest -q
cleanroomx-gui --demo
```

Under Xvfb on Linux, CI also executes:

```bash
xvfb-run -a -s "-screen 0 1920x1080x24" python tools/capture_design_studio_ci.py --width 1536 --height 960 --output reports/studio-preview/cleanroomx-design-studio-1536x960.png
xvfb-run -a -s "-screen 0 1920x1080x24" python tools/capture_design_studio_ci.py --width 1920 --height 1080 --output reports/studio-preview/cleanroomx-design-studio-1920x1080.png
```

These outputs are genuine application captures **only if** the corresponding
CI jobs succeed and the saved images are actually reviewed. The screenshot
utility checks real room polygons exist before capture.

## Open limitations / next review

- The GitHub change cannot inspect an unsaved local Windows checkout or
  the working tree at `C:\Users\omar\CleanroomX-Cleanroom-Design-Simulation-Verification-Platform`.
- GUI is canvas-projected, not a GPU surface with real alpha transparency;
  image matching remains incomplete even when the Tk tests pass.
- OpenFOAM full end-to-end CFD verification is separate from the visual/UI
  changes; keep its completion status **unverified** here.
- Inspect the PR's most recent CI artifacts and full regression results;
  fix failing tests before acceptance, then compare 1920 × 1080 images.
