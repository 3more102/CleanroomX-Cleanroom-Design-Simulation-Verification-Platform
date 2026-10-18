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

**Verified on Linux under Xvfb:** full-size 1920×1080 real Tk baseline/after screenshots were captured with successful [GUI Reference Capture run 39170476299](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/39170476299). Receipts independently record actual root-window 1920×1080, Output panel hidden in both, 3D viewport **993×688 before** / **993×619 after**, selected Process room, real demonstration geometry, and no solver execution. The difference report found **289116 of 2073600 pixels** changed at RGB threshold 10; this compares before/after builds, **not** either image against the user reference. Source-controlled capture script and 14-day CI ZIP artifacts enable independent review. **Not yet verified:** Windows desktop rendering, manual selection click tests, full reference-image parity, full regression, and end-to-end OpenFOAM execution.

No exact visual-parity percentage, full GUI completeness percentage or OpenFOAM integration percentage is claimed. A denominator must be defined by a reviewed test matrix, and each criterion independently checked before calculating any percentage. "Unknown" is not equivalent to 0% or 100%.

## Reference-demo model check

The mathematical model contract test uses **three synthetic model rooms**, `Process` (6×5×3 m), `Preparation` (5×4×3 m) and `Ante/Airlock` (4×3×3 m), with ten placed objects. The helper must derive (not store) the totals **3 rooms**, **62 m²**, **186 m³** and **10 placed objects**. These synthetic fixtures do not claim that the bundled project has identical geometry.

## Acceptance matrix

| Acceptance criterion | Implementation | Verification |
| --- | --- | --- |
| Four live model metrics | Added | Isolated model test passed; values visually confirmed in real Tk capture |
| Room Navigator floorplan and click selection | Added | Focused Tk test suite passed in run 39171024414; full manual selection audit pending |
| Selected Room overview | Added | Selected Process room visible with configured pressure in genuine Tk capture |
| Categorized device counts | Added | Isolated model test passed |
| Focus / Isolate / Restore controls | Reuses existing real operations | Focused Tk test suite passed in run 39171024414 |
| Studio View / Inspector controls | Connected | Both shown in real GUI screenshot; manual mouse-click acceptance pending |
| 2D / 3D / Split | Existing implementation retained | Full regression pending |
| Visual parity with reference screenshot | Unverified | Genuine before/after screenshots captured; user-reference image was not available to CI |
| OpenFOAM integration | Existing separate backend unchanged | End-to-end solver evidence required |
| Test suite regression | Focused tests committed | Screenshot CI passed; full application CI still pending |

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

Genuine 1920×1080 screenshots have now been captured through `scripts/capture_gui_reference_parity.py` and preserved as Actions artifacts in run 39170476299. Continue with screenshot **reference** comparison and hands-on Windows acceptance; preserve image receipts with commit SHA and exact run results. Do not treat before/after pixel differences as reference parity.

## Next priorities

1. Finish new Tk and existing spatial/GUI CI checks, fix failures and record actual pass/fail/skip counts.
2. Audit genuine 1920×1080 screenshots, especially the reference's larger 3D-first central workspace, room labels, typography and density at smaller resolutions.
3. Add genuine device markers, wall transparency, door openings and any missing geometric behavior based on the existing model; never substitute bitmap imagery.
4. Validate actual OpenFOAM Foundation v10 case generation/execution/results/diagnostics end to end, and only present solver-derived fields that have run receipts.
5. After evidence, calculate completion fractions from a publicly inspectable acceptance checklist; do not infer parity from committed code alone.

## Captured CI evidence (not a final reference-parity verdict)

- [Genuine before/after screenshots and receipts, successful run 39170476299](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/39170476299) — artifact `gui-reference-parity-before-after`.
- Before real 3D canvas: **993×688 px**; after: **993×619 px**, at the same application window **1920×1080 px**. The 69 px reduction is occupied by the new live dashboard/Studio controls, not improved 3D viewport height.
- Displayed project data: three rooms, 62 m², 186 m³, 10 placed objects. Pressure in the Selected Room panel is explicitly marked configured.
- No verified human review of the user-supplied reference image; no OpenFOAM solver executed during screenshot capture.

## Focused actual-Tk acceptance result

GitHub Actions [GUI Reference Capture run 39171024414](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/39171024414) executed `xvfb-run -a -s "-screen 0 1920x1080x24" python -m pytest -q after/tests/test_gui_design_studio.py` and reported **5 passed in 1.25 seconds; 0 failed; 0 skipped**. This includes the pure model contract and Tk workspace cards/selection/isolation/visibility tests. The same workflow then captured genuine full-size GUI screenshots. These checks do not establish all required visual and engineering acceptance criteria.
