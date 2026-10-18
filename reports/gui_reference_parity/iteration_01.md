# GUI Reference Parity — Iteration 01 Evidence Record

Date: 2026-10-19 (Egypt)  
Branch: `chatgpt/gui-reference-parity-stage1-20261019`  
Draft review: https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/pull/1351

## Model and implementation audit

The working application uses real Tk Canvas room projection with normalized
project geometry. `layout_metrics` derives counts directly from project data.
The bundled reference demo contains:
- Process: 6 × 5 × 3 m, 30 m², 90 m³.
- Preparation: 20 m²; height and other values from canonical room geometry.
- Ante / Airlock: 12 m²; height and other values from canonical room geometry.
- Total 3 rooms, floor area 62 m², geometric volume 186 m³.
- Ten normalized device/opening records (doors included by counting policy).

## Implemented in feature branch

- Live Rooms, Floor Area, Geometric Volume, Placed Devices.
- Live selected-room classifications, dimensions, volume, assigned devices,
  configured pressure explicitly distinct from any solver result.
- Categorized device/opening totals.
- 2D Room Navigator embedded over the actual live 3D model; clicking a room
  synchronizes the model selection and Inspector, and highlights the 2D/3D views.
- Room focus, isolation, restore all, Inspector toggle and Studio View.
- Immersive, dark demo startup with large 3D model, room selected and
  Inspector shown, with external panes hidden. Ordinary project startup
  keeps the user's existing panel choices.
- Engineering legend uses the selected light/dark theme palette and avoids
  obscuring the top summary cards.
- Navigator label shortening avoids overflow in small room rectangles.
- Focused regression cases for real model edits, undo, navigator and panels.
- Screenshot capture script records original rendered Tk pixels via `scrot`
  on Xvfb, NOT a fabricated/illustrated UI.

## CI evidence collected

- The first new UI run exposed three regressions in compact layout:
  **58 passed, 3 failed**. All three were fixed.
- After those fixes, GitHub Actions Xvfb:
  **61 passed, 0 failed** (run 39169513254).
- After adding immersive demo regression coverage:
  **62 passed, 0 failed** and genuine 1920 × 1080 screenshot
  (run 39170287686).
  https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/39170287686
- Later adjustments may have their own CI runs; final evidence must be read
  from the workflow for the final commit SHA. Earlier passes do not
  automatically validate future commits.

## Visual review (real 1920 × 1080 screenshot)

- The initial captured GUI had a vertically compressed 3D viewport with the
  outside Project Navigator and Output / Verification panels using large areas.
- A subsequent real screenshot verifies the immersive view expands the 3D
  viewport; the three projected rooms, navigator, live summary cards and
  Process-room Inspector are all present.
- Remaining visual issues: typography/proportions must be compared to the
  actual supplied reference; verify on Windows. Existing Tk projected model
  has solid walls and does not establish transparent volumetric CFD rendering.
- Last adjustment targets collision between the native engineering legend
  and the new cards and overlapping small navigator room labels; fresh
  screenshot verification is required.

## Evidence gap / acceptance matrix

| Area | Current evidence | Acceptance |
|---|---|---|
| Demo loads, 3 rooms | Real Tk test and screenshots | Proven under Xvfb |
| 62 m², 186 m³, 10 records | Source model + regression tests | Proven for bundled demo |
| Live card updates on edit/undo | Real Tk regression test | Proven for tested operations |
| Navigator→selection→inspector | Real Tk regression test | Proven for tested operation |
| Studio/focus/restore controls | Real Tk regression test | Proven for tested operations |
| Dark immersive 3D view | Real screenshot + Tk pane checks | Proven under Linux/Xvfb |
| Exact visual match to supplied reference | No pixel correspondence measurements | NOT VERIFIED |
| Actual Windows installation and GUI | External Windows desktop inaccessible | NOT VERIFIED |
| 3D transparent walls & true door apertures | Not explicitly implemented in this iteration | NOT VERIFIED |
| Real OpenFOAM Foundation v10 run and field provenance | No solver execution in this iteration | NOT VERIFIED |
| Full repository regression suite | Separate PR CI, not guaranteed passed | NOT VERIFIED |
| Release readiness and absence of high severity defects | Requires full engineering review | NOT VERIFIED |

Percentages: withheld until each category has a documented and actually
assessed denominator. Do not confuse focused test pass rate with total GUI
completion or OpenFOAM integration.

## Commands for the user's Windows environment

```powershell
cd C:\Users\omar\CleanroomX-Cleanroom-Design-Simulation-Verification-Platform
git fetch origin
git switch chatgpt/gui-reference-parity-stage1-20261019
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_gui_reference_parity_stage1.py tests/test_spatial_editing_gui.py
cleanroomx-gui --demo
```

This report records checked evidence, not a claim of 100% reference parity or
complete solver integration.
