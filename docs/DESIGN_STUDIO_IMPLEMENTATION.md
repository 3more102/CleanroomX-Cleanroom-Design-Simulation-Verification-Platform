# Real Design Studio integration (development branch)

Branch: `feat/real-design-studio-20261018`. The interface is an actual Tkinter
application view layered over the existing `SpatialDesignWorkspace` and project
model. It does **not** replace the spatial editor or use mock engineering data.

## Architecture and data provenance

- `src/cleanroomx/gui_design_studio.py` provides the Studio dashboard,
  selected-room detail, room mini-plan and camera controls.
- `src/cleanroomx/spatial.py` retains the canonical 2D/3D renderer, project
  layout, interactive selection, undo/redo, edit commands, engineering overlays,
  data synchronization and geometry validation.
- `studio_snapshot(layout, room_id)` derives the counts, areas, volumes and
  placed-device summaries from the **current normalized spatial layout**.
  Unset pressures display **Not specified**, never simulated values.
- Room navigator, floor-plan rectangles and the 3D canvas all call the existing
  `select_item(..., notify=True)` route. **Focus Room** uses a real
  single-room 3D camera fit, **Isolate Room** uses the existing spatial visibility
  filter, and **Studio View** restores the full suite and a balanced model fit.
- Pressure relationships and engineering overlays still depend on the supplied
  project/analysis data. OpenFOAM, reporting and verification tabs remain
  accessible from the existing notebook and application menus.
- The bundled demo now opens with **dark theme / 3D / Focus Workspace** on
  `cleanroomx-gui --demo`. The View menu allows users to restore external
  navigation/output panels. Default Studio chrome has **View**, **Balance**,
  **Studio View**, **Inspector** and **More tools**, while the original 2D/Split
  modes, floor editor, engineering sync and advanced overlays remain accessible.
  Navigator and inspector widths adapt to smaller desktop viewports.

## Visual reference comparison

| Target detail | Implemented state |
| --- | --- |
| Navy Studio/dashboard presentation | Dark themed Studio with cyan/teal accents |
| Live room, floor area, volume, device cards | Derived from current project layout |
| In-view Room Navigator and selectable floor mini-map | Real room geometry and room-select callbacks |
| Selected Room details and per-room device counts | Real room dimensions, pressure and device ownership |
| Focus Room / Isolate Room / Inspector / Studio View | Commands wired to actual spatial/application actions |
| 3D color-coded rooms, labels, openings and devices | Roofless architectural cutaway with real room floors, smooth blended far walls, room title chips and model-dimensioned opening outlines |
| 2D tools, geometry edits, undo/redo, overlays | Retained through original workspace and More tools |
| CFD/OpenFOAM, save, verification, reporting | Unmodified underlying application/backend |

### Remaining visual differences

Tk Canvas polygons do not support true RGBA alpha: the Studio approximates
the reference's see-through cutaway with **open ceilings, omitted near walls,
model-colored opaque floors and smoothly blended far walls**. The camera-facing
wall choice updates with azimuth. This is a 2D-canvas 3D projection, **not**
physically correct multi-layer alpha blending or a GPU 3D mesh. A few fonts,
icons, toolbar rows and scene details still differ. No pixel-perfect claim
is made.

Projected door/transfer outlines are display annotations, not Boolean wall
cut-outs or proof of a manufacturable architectural model.

## Verification

- `tests/test_gui_design_studio.py`: deterministic data snapshots plus real Tk
  3D canvas, navigator selection, room isolate and advanced-controls checks.
- `tests/test_spatial_editing_gui.py`: existing real Tk engineering editing tests
  adjusted for the compact default inspector and hidden advanced rows.
- `.github/workflows/design-studio-preview.yml`: Xvfb-based real GUI tests and
  screenshot taken from the **running application** using Pillow ImageGrab.
- `tools/capture_design_studio_ci.py`: capture helper checks that the demo
  actually drew spatial room polygons before saving a screenshot.
- The follow-up preview captures a **1920×1080** Full HD running application screenshot,
  as required by the acceptance campaign. The original supplied reference can
  have a different resolution; visual comparison must account for that rather
  than claiming pixel-exact correspondence. Review the latest workflow artifact.
- Full repository CI includes Python 3.11, 3.12 and 3.13 test matrices,
  Windows launcher smoke, and installed-wheel GUI smoke. Require all checks
  to pass for the latest revision before merging.

## Launch from a separate Windows worktree (does not overwrite current work)

Run in the existing CleanroomX repository:

```powershell
git fetch origin
git worktree add "..\CleanroomX-Studio" origin/feat/real-design-studio-20261018
cd "..\CleanroomX-Studio"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\cleanroomx-gui.exe --demo
```

If the separate worktree path already exists, select a different unused path.
Do not reset, stash or overwrite the original checkout to review this branch.

## Navigator parity follow-up

The navigator cache now uses room position, length and width as well as identity,
name and selection. Movement and equal-area aspect-ratio edits therefore refresh
the miniature plan. An explicit **Restore all rooms** action clears isolation,
and inspector pressure is labeled **Configured pressure** to avoid implying
OpenFOAM-computed evidence. Acceptance status and verification gates are tracked
in [`GUI_REFERENCE_PARITY.md`](GUI_REFERENCE_PARITY.md).
