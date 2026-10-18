# CleanroomX Design Studio — Reference Parity

Date: 2026-10-19  
Implementation branch: `chatgpt/gui-reference-parity-stage1-20261019`  
Starting point: `work/cfd-integration-reconciliation-20261018` (not the older `main`)

## Evidence policy

An implementation in source control is **not** proof that the GUI launched, the
screen matches the supplied reference, or an OpenFOAM solver ran. Those claims
need actual run logs and original screenshots from the installed application.
A genuine application screenshot was captured under Xvfb at 1920 × 1080;\nsee [iteration evidence](../reports/gui_reference_parity/iteration_01.md).\nThis is not evidence of native Windows launch or exact pixel parity.

## Observed baseline (repository inspection)

- Desktop interface: Tkinter/ttk with real Canvas-based 2D and projected 3D
  room/device geometry in `src/cleanroomx/spatial.py`.
- GUI entry point: `cleanroomx.gui:main` (`cleanroomx-gui --demo`).
- Existing live editor: room/device edits, save/reload, 2D/3D/Split views,
  selection, overlays, inspector fields, isolation, history and camera controls.
- The external project navigator already exists in `gui.py`; the reference
  **embedded** mini navigator and four separate top-level summary cards were
  missing in the inspected starting code.
- The bundled demo contains Process, Preparation and Ante / Airlock; geometry
  totals calculated directly from its spatial metadata are **3 rooms,
  62 m², 186 m³, 10 device/opening records**.

## Iteration 1: Changes implemented in code

| Feature | Source implementation | Run/visual evidence |
|---|---|---|
| Four live model-derived cards | Implemented | Focused Xvfb Tk suite passed |
| Room count/area/volume updates | Implemented using `layout_metrics` | Focused Xvfb Tk suite passed |
| Placed-device categories | Implemented (FFU/Supply/Return+Exhaust/Other) | Focused Xvfb Tk suite passed |
| Embedded 2D Room Navigator | Implemented from current room rectangles | Genuine Xvfb 1920×1080 screenshot captured |
| Click-to-select navigator→inspector/2D/3D | Implemented via `select_item` | Focused Xvfb Tk suite passed |
| Selected room dimensions, classification, device count | Implemented | Focused Xvfb Tk suite passed |
| Configured pressure distinction | Labelled **configured pressure**, never solver result | Focused Xvfb Tk suite passed |
| Focus Room | Implemented using existing synchronized camera fit | Focused Xvfb Tk suite passed |
| Isolate/Restore | Existing implementation, surfaced in inspector | Focused Xvfb Tk suite passed |
| Studio View (isometric/full/inspector) | Implemented | Focused Xvfb Tk suite passed |
| Inspector toggle | Implemented | Focused Xvfb Tk suite passed |
| OpenFOAM live simulation & verified fields | Not changed this iteration | **Not verified** |
| Precise reference screenshot parity | Not measured | **Not verified** |

Counting policy: Placed Devices is the total number of normalized
`layout['devices']` records, including doors, windows, openings and
transfers. Other/Openings includes every normalized category other than FFU,
Supply, Return and Exhaust. Device counts are separate from solver metrics.

## Acceptance/verification commands

From the repository root on a machine with a Tk display:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_gui_reference_parity_stage1.py
python -m pytest -q tests/test_spatial_editing_gui.py tests/test_gui_theme.py
python -m pytest -q
cleanroomx-gui --demo
```

For CI Linux GUI testing, execute the focused tests with `xvfb-run -a`
rather than treating no-DISPLAY skips as passed GUI interactions.

## Unverified visual work

1. Capture a *Windows-native* screenshot and compare to the exact supplied
   reference image; Linux Xvfb screenshot alone is not Windows parity.
2. Check typography, palette, room proportions, door apertures and translucent walls.
3. Run the full suite and record exact pass/fail/skip/error counts at the final SHA.
4. Verify OpenFOAM v10 installed solver separately with provenance-backed
   residuals and fields; never infer integration % from GUI widgets.

## Percent completion

**Not reported yet.** A numeric percent without a reviewed acceptance
denominator plus actual GUI and solver evidence would be misleading.
Criteria and per-item evidence must be recorded before calculating any score.

## Limitations

GitHub repository code was inspected and changed through the connected
repository interface. The user's Windows desktop is not accessible to this
session. The app **was launched in a real Linux/Xvfb GUI session**, with an
unmodified screenshot recorded as a GitHub Actions artifact. **It was not
launched on the user's Windows desktop** and exact screenshot parity is
unverified. The external reference screenshot was not available as an exact
comparison asset in this session.

Latest verified focused evidence before the most recent cosmetic adjustment:
**62 passed, 0 failed** in GitHub Actions run
[39170287686](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/39170287686).
The cosmetic correction requires its own fresh CI evidence.
