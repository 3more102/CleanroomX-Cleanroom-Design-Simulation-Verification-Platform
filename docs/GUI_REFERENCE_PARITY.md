# GUI Reference Parity — Implementation Evidence

## Scope and branch

- Working branch: `chatgpt/gui-reference-parity-phase1-20261019`.
- Base: `work/cfd-integration-reconciliation-20261018`.
- GUI: Tkinter / ttk, `SpatialDesignWorkspace` in `src/cleanroomx/spatial.py`.
- This is **Phase 1**, not a claim of complete screenshot parity.

## Implemented in Phase 1

1. Model-backed Design Studio cards for **Rooms**, **Floor Area**, **Geometric Volume**, and **Placed Devices**, refreshed by the existing spatial redraw path. Summaries are not hardcoded to a demo project.
2. Live right-side **Selected Room** overview: name, classification, L×W×H, area, volume, placed-object count and **configured** design pressure; no CFD result is inferred from that field.
3. Live categorized **Placed Devices** overview for FFU, supply, return/exhaust, and other (including openings). Counting policy: every object in the canonical `devices` array counts once.
4. Miniature **Room Navigator** drawn from real X/Y room footprints in the 3D view. Room clicks call the existing `select_item("room", id, notify=True)` and therefore share selection with the application project tree and 2D/3D canvases.
5. **Focus Room**, **Isolate Room**, **Restore All Rooms**, **Studio View**, and **Inspector** controls call pre-existing, real spatial methods (no mock canvas).
6. Focused unit tests and Xvfb/Tk tests added to the CI workflow.

### Existing functionality retained

Project/analysis tabs; 2D, 3D and Split views; canvas editing, orbit/pan/zoom, section and projection controls; history, save/reload, validation, independent OpenFOAM UI. No solver code or engineering semantics were changed by this patch.

## Verification / limitations

**Verified in an isolated local Python test**, before uploading the equivalent pure-model helper: three tests passed, zero failed. These exercises are **not** a full repository test run.

**Not verified in this environment:** launching the Windows desktop build; `cleanroomx-gui --demo`; a true 1920×1080 baseline/after screenshot; 2D/3D and navigator interactive mouse clicks; overall regression counts; an end-to-end OpenFOAM solver run. GitHub Actions Xvfb runs should be used to validate the new Tk tests; the result must be recorded after the checks finish.

No exact visual-parity percentage, full GUI completeness percentage or OpenFOAM integration percentage is claimed. A denominator must be defined by a reviewed test matrix, and each criterion independently checked before calculating any percentage. "Unknown" is not equivalent to 0% or 100%.

## Reference-demo model check

The mathematical model contract test uses **three synthetic model rooms**, `Process` (6×5×3 m), `Preparation` (5×4×3 m) and `Ante/Airlock` (4×3×3 m), with ten placed objects. The helper must derive (not store) the totals **3 rooms**, **62 m²**, **186 m³** and **10 placed objects**. These synthetic fixtures do not claim that the bundled project has identical geometry.

## Acceptance matrix

| Acceptance criterion | Implementation | Verification |
| --- | --- | --- |
| Four live model metrics | Added | Isolated model test passed; actual GUI run pending |
| Room Navigator floorplan and click selection | Added | Tk integration test committed; execution pending |
| Selected Room overview | Added | Model test passed; GUI execution pending |
| Categorized device counts | Added | Isolated model test passed |
| Focus / Isolate / Restore controls | Reuses existing real operations | Tk integration test committed; execution pending |
| Studio View / Inspector controls | Connected | Real GUI screenshot and click acceptance pending |
| 2D / 3D / Split | Existing implementation retained | Full regression pending |
| Visual parity with reference screenshot | Unverified | Real same-size screenshots and review required |
| OpenFOAM integration | Existing separate backend unchanged | End-to-end solver evidence required |
| Test suite regression | Focused tests committed | CI and full suite pending |

## Local reproduction (Windows PowerShell)

```powershell
cd 'C:\Users\omar\CleanroomX-Cleanroom-Design-Simulation-Verification-Platform'
git fetch origin
git switch chatgpt/gui-reference-parity-phase1-20261019
python -m pip install -e '.[dev,cfd]'
python -m pytest -q tests/test_gui_design_studio.py tests/test_spatial_editing_gui.py tests/test_gui.py
cleanroomx-gui --demo
```

For a Linux CI/test host:

```bash
python -m pytest -q tests/test_gui_design_studio.py -k 'not real_studio and not studio_live'
xvfb-run -a python -m pytest -q tests/test_gui_design_studio.py -k 'real_studio or studio_live'
```

Capture genuine 1920×1080 screenshots using the existing GUI capture tooling; compare geometry, main workspace proportions, toolbar positions, cards, room navigator and selection states. Preserve source, real screenshot identifiers, commit SHA and the exact run results with the report.

## Next priorities

1. Run new Tk tests and all existing spatial/GUI tests; fix failures and record actual pass/fail/skip counts.
2. Audit genuine 1920×1080 screenshots, especially the reference's larger 3D-first central workspace, room labels, typography and density at smaller resolutions.
3. Add genuine device markers, wall transparency, door openings and any missing geometric behavior based on the existing model; never substitute bitmap imagery.
4. Validate actual OpenFOAM Foundation v10 case generation/execution/results/diagnostics end to end, and only present solver-derived fields that have run receipts.
5. After evidence, calculate completion fractions from a publicly inspectable acceptance checklist; do not infer parity from committed code alone.
