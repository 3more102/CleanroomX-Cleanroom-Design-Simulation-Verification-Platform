# CleanroomX Design Studio — reference parity

Status: **IN PROGRESS / NOT ACCEPTED**  
Baseline: upstream main at cf5506ffc5793313e023118209faafefc17e73b7 (remote observation, 2026-10-19).  
Implementation: branch gui/design-studio-reference-parity-20261019.  

## Source of truth

The supplied reference depicts an integrated dark navy/cyan Design Studio, with
three sample rooms (Process, Preparation, Ante / Airlock), room navigator, live
metrics and room/device inspector. The bundled project
src/cleanroomx/demo/gui_demo.cleanroomx.json contains exactly 3 rooms,
62 m² combined floor area, 186 m³ volume and 10 devices/openings.

Values in the application must be calculated from the canonical spatial_layout,
not embedded as demo-specific constants. Pressure is a configured setpoint
unless an independently valid simulation result says otherwise.

## Baseline audit

- The executable entrypoint is cleanroomx-gui = cleanroomx.gui:main in pyproject.toml.
- The GUI uses Tkinter/ttk; the spatial 3D view is Canvas-based projected geometry,
  not a native GPU mesh renderer.
- Existing spatial code supports 2D/3D/split, selection, editing, fit,
  projection presets, camera orbit/pan/zoom, section plane, hiding and isolation.
- Existing engineering overlay code distinguishes analysis and solver result data.
- An unmodified 1920×1080 Windows screenshot **has not been captured** here.
  The remote GitHub connection cannot open the user's Windows desktop or inspect
  uncommitted local changes, so pixel parity is **unverified**.

## Current implementation

- Added studio_summary.dashboard_snapshot to calculate four live cards and the
  selected room facts from room geometry and assigned devices. Return and exhaust
  are grouped together; Other includes all remaining device/opening types.
- Added studio_summary.navigator_rectangles, preserving aspect ratio and relative
  room positions in a miniature top-down plan.
- Embedded the navigator as an interactive Tk Canvas over the live 3D viewport.
  Clicking a room selects the same object used by the 2D/3D views and Inspector.
- Added Focus Room, Isolate Room, Restore All, Studio View and Inspector actions,
  delegating to existing spatial methods.
- Added a selected-room summary which labels pressure as a configured **setpoint**.
- Improved the existing optional dark palette to navy/cyan. Existing persisted
  user theme choices are preserved; dark mode must be selected for screenshot
  comparison against the dark reference.
- Added tests/test_design_studio_reference.py for the demo, live calculations,
  navigator, 3D workspace actions and duplicate workflow.

## Acceptance matrix

| Criterion | Implementation observation | Verification evidence |
| --- | --- | --- |
| App launches, demo loads | Existing infrastructure | Pending fresh run |
| Four live cards | Implemented on branch | Tests added; results pending |
| Room navigator miniature floor plan | Implemented on branch | Tests added; GUI click pending runtime check |
| 2D/3D/navigator selection | Uses existing selection callback | Pending end-to-end GUI run |
| Selected-room inspection | Implemented; derived model facts | Tests added; results pending |
| Device categorization | Implemented including doors/openings | Tests added; results pending |
| Focus/isolate/restore | Uses existing spatial functions | Tests added; results pending |
| Studio 3D workspace | Integrates existing 3D canvas | Pending 1920×1080 inspection |
| Dark/navy/cyan appearance | Palette and card styles updated | Pixel-level visual parity unverified |
| Create/edit/save/reload | Existing editor/persistence preserved | Pending full regression |
| OpenFOAM CFD fields and residuals | No change to solver integration | Not tested for this iteration |
| No high-severity regression | Unknown | Full suite not yet executed |
| Actual Windows before/after captures | Not available remotely | Required before acceptance |

## Evidence-based completion policy

Do not publish percentages based on code size or the mere existence of controls.
Use the following **denominators and pass rules** only after evidence collection:

1. Visual parity: 15 reference components individually reviewed against genuine
   1920×1080 before/after screenshots; pass requires both presence and legibility.
2. GUI functional completeness: 20 documented user workflows, each exercised
   end to end with checked visible and persisted state.
3. 3D interaction coverage: 10 gestures/actions validated against geometric state.
4. Room/device synchronization: 8 changes, each confirmed across navigator,
   inspector, scene and saved/reloaded project.
5. OpenFOAM integration: version-scoped feature matrix, passing only if a
   real solver run provides independently attributable, parsed output; denominator
   must list all claimed capabilities, never infer an overall percentage.
6. Automated verification: number of required test cases that passed divided
   by total required cases; report skipped separately and never count them passed.

All six percentages are **NOT MEASURED** at this stage: acceptance executions and
the reference screenshot comparison are incomplete.

## Reproduce on Windows

In PowerShell, from the existing repository checkout:

```powershell
git status --short
git fetch origin gui/design-studio-reference-parity-20261019
git switch gui/design-studio-reference-parity-20261019
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_design_studio_reference.py tests/test_spatial.py tests/test_gui_theme.py
python -m pytest -q
cleanroomx-gui --demo
```

Select dark mode in the GUI, open Design Studio, set the real application
window to 1920×1080 and capture an unmodified screenshot. Confirm click
selection, room edit and save/reload. Never use a generated image as evidence.

**Release gate: HOLD** until screenshot parity, visual review, focused and full
regressions, and real OpenFOAM integration evidence are recorded.
