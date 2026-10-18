# CleanroomX GUI Reference Parity — Engineering Ledger

## Scope and audit (2026-10-19)

Target: the supplied original Design Studio screenshot, with dark navy/cyan styling,
3D Process / Preparation / Ante-Airlock rooms, model-derived summary cards,
a Room Navigator and selection-aware engineering Inspector.

Remote code audit completed against `main`, using the connected GitHub repository.
**Local Windows state, uncommitted files, baseline screenshots, OpenFOAM
execution and live GUI visual parity were NOT observable from this session.**
No local application, solver or regression test execution is claimed.

Existing components preserved: Python/Tkinter + ttk application,
`src/cleanroomx/gui.py` shell, canonical spatial metadata and project history,
`src/cleanroomx/spatial.py` 2D/3D Canvas workspaces, 3D camera projections,
engineering overlays and backend run/validation machinery.

The bundled demo, `src/cleanroomx/demo/gui_demo.cleanroomx.json`, already
contains exactly 3 rooms (Process 6×5×3 m, Preparation 5×4×3 m and
Ante/Airlock 4×3×3 m) and 10 placed objects. Expected geometry-derived
totals: 62 m² floor area and 186 m³ volume.

## Iteration 001 — implementation

- Four actual model-driven cards above the design viewport: Rooms, Floor Area,
  Geometric Volume and Placed Devices. Calculations reuse the canonical spatial
  normalization/metrics layer. All placed items, **including openings**, count.
- Selectable, geometry-proportional mini floor plan embedded in the 3D
  viewport. It shares room IDs with the 2D/3D scene and existing project
  navigator; selecting a mini-plan room uses the same selection handler.
- Selected Room overview with dimensions, classification, area, volume,
  room placement count and **configured** design pressure, never fabricated CFD
  pressure. Placed Devices overview groups FFU, supply, return/exhaust and other.
- Live room/device ID/name/type search that cycles real matching objects without changing geometry.
- Real Focus Room, Isolate, Show All and Studio View actions. Studio View
  selects the existing 3D workspace, reveals the inspector, fits the model and
  applies a dedicated navy/cyan Studio theme without altering existing light/dark presets.
- Real widget contract tests added to `tests/test_gui_reference_studio.py`
  and linked into the Tk/Xvfb CI stage. The existing project persistence,
  validation, 2D/3D renderer and solver APIs were not replaced.

### Acceptance matrix

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Model-derived four cards | Implemented | CI and desktop verification pending |
| Room Navigator geometry and click-selection | Implemented | CI and desktop verification pending |
| Selected-room live inspector | Implemented | CI and desktop verification pending |
| Categorized placed device counts | Implemented | CI and desktop verification pending |
| Focus / isolate / show all / Studio View | Implemented using existing camera and visibility APIs | CI and desktop verification pending |
| Responsive visual comparison at 1920×1080 | Not yet established | Genuine Windows screenshot required |
| Fully matched typography, spacing, navy/cyan palette | Not yet established | Screenshot-to-reference review required |
| OpenFOAM execution, mesh and CFD result parity | Not changed in this iteration | End-to-end OpenFOAM v10 evidence required |
| Entire GUI + CFD regression suite | Not run in this session | CI and Windows runs required |

No fabricated numerical percent: the denominator must be a frozen list of
independently testable acceptance criteria per category. Proposed scoring:
**completed and verified / total applicable criteria × 100**, counting an
item only after real execution evidence is attached. Until then each category
is **not measured**, not 100%:

| Category | Current evidence-based percentage |
| --- | --- |
| Visual reference parity | Not measured — no genuine screenshot comparison |
| GUI functional completeness | Not measured — full acceptance suite not run |
| 3D interaction coverage | Not measured — focused coverage pending |
| Room/device synchronization | Not measured — CI and desktop checks pending |
| OpenFOAM integration | Not measured in this GUI iteration |
| Automated verification | Not measured — CI / complete regression pending |

## Verification commands

From a Python-enabled checkout, with Tk/Xvfb on Linux or a working desktop on
Windows:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_spatial.py tests/test_gui_reference_studio.py
# Linux desktop test harness:
xvfb-run -a python -m pytest -q tests/test_spatial_editing_gui.py tests/test_gui_reference_studio.py
cleanroomx-gui --demo
```

On Windows PowerShell:
```powershell
Set-Location "C:\Users\omar\CleanroomX-Cleanroom-Design-Simulation-Verification-Platform"
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_spatial_editing_gui.py tests/test_gui_reference_studio.py
cleanroomx-gui --demo
```

Visual QA: use the original user-provided reference screenshot and a genuine
1920×1080 capture of `cleanroomx-gui --demo`, select **Studio View**,
confirm all four totals, 3D geometry, mini-plan, Inspector, then compare the
screenshots. Repeat at 1050×680 for clipping/regression review.

## Next unmet engineering gates

1. Real desktop screenshot and before/after comparison; correct layout,
   mini-plan occlusion, font scaling and panel scroll/clipping where observed.
2. CI result and focused/full regression receipts with exact pass/fail/skip.
3. Geometry editing, save/reopen and synchronized selection acceptance.
4. Independent OpenFOAM v10 case generation → solver → parsed fields/diagnostics
   evidence and explicit simulation freshness classifications.
5. Updated screenshots and review of residual critical/high defects before
   declaring reference parity.

**Release state: IN PROGRESS; NOT visually verified; NOT CFD-complete.**
