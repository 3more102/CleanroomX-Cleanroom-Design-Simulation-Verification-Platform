# CleanroomX Design Studio — Reference Parity

Date: 2026-10-19  
Implementation branch: `chatgpt/gui-reference-parity-stage1-20261019`  
Starting point: `work/cfd-integration-reconciliation-20261018` (not the older `main`)

## Evidence policy

An implementation in source control is **not** proof that the GUI launched, the
screen matches the supplied reference, or an OpenFOAM solver ran. Those claims
need actual run logs and original screenshots from the installed application.
No screenshots were generated or asserted in this iteration.

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
| Four live model-derived cards | Implemented | Pending headless GUI execution |
| Room count/area/volume updates | Implemented using `layout_metrics` | Pending GUI regression |
| Placed-device categories | Implemented (FFU/Supply/Return+Exhaust/Other) | Pending GUI regression |
| Embedded 2D Room Navigator | Implemented from current room rectangles | Pending screenshot |
| Click-to-select navigator→inspector/2D/3D | Implemented via `select_item` | Pending GUI regression |
| Selected room dimensions, classification, device count | Implemented | Pending GUI regression |
| Configured pressure distinction | Labelled **configured pressure**, never solver result | Pending GUI regression |
| Focus Room | Implemented using temporary visibility filter and 3D fit | Pending GUI regression |
| Isolate/Restore | Existing implementation, surfaced in inspector | Pending GUI regression |
| Studio View (isometric/full/inspector) | Implemented | Pending GUI regression |
| Inspector toggle | Implemented | Pending GUI regression |
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

1. Capture original unmodified reference baseline and new application screen
   at 1920×1080 using the user's native desktop or a real GUI session.
2. Compare panel placement, typography, color palette and 3D room dimensions.
3. Verify the original user's theme preference is preserved; dark default
   parity and responsive geometry remain open.
4. Record exact focused/full suite passed, failed, skipped and error counts.
5. Verify the OpenFOAM v10 installed solver separately with provenance-backed
   residuals and fields; never infer integration % from GUI widgets.

## Percent completion

**Not reported yet.** A numeric percent without a reviewed acceptance
denominator plus actual GUI and solver evidence would be misleading.
Criteria and per-item evidence must be recorded before calculating any score.

## Limitations

GitHub repository code was inspected and changed through the connected
repository interface. The user's Windows desktop is not accessible to this
session. Consequently the application was **not** launched locally and no
authentic baseline/after screenshot was captured in this iteration.
