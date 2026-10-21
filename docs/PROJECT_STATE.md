# CleanroomX engineering state — 21 October 2026

## Native residual inspection increment

The existing desktop residual panel now supports actual field/kind/scale
controls, recent recorded-iteration windows and exact mouse/keyboard probes.
Repeated linear solves remain distinct; initial limits are not applied to
final linear residuals. The [current report](../reports/native-residual-inspection-20261021/REPORT.md)
records **2843 passed / 0 failed / 24 capability skips** on a real Tk/VTK display.
The skips are actual Foundation v10 execution and optional native IFC, unavailable
in this environment. [Three new actual GUI captures](native-residual-inspection-20261021/README.md)
reuse the verified archived 100-iteration case, which remains unconverged.
This increment does not claim a new solver run. Engineering release remains
**HOLD**; earlier complete solver-enabled results below retain their original scopes.

## Native cancellation and GUI lifetime recovery

The [current execution report](../reports/native-cancellation-20261021/REPORT.md)
records **2833 passed / 0 failed / 1 optional IFC skip** with actual Foundation
v10 and a Tk/VTK display. Native solver cancellation now cleans up its managed
POSIX process group, retains cancelled receipts and refuses partial imports.
Real solver regressions include Ctrl+C and closing the entire Tk application.
A complete-suite Tk variable finalization crash led to a main-thread GUI
lifetime boundary and targeted ownership regressions. Two actual current
desktop captures and an original cancelled-case archive are retained.
The report also retains a separately rejected incomplete mesh attempt whose
cause is unresolved. Windows-to-WSL cancellation and physical CFD qualification
remain open; engineering release remains **HOLD**. The earlier results below
are historical evidence with their original scopes.

## Startup and runtime recovery increment

The [current recovery report](../reports/startup-runtime-recovery-20261021/REPORT.md)
records source changes, **2812 passed / 0 failed / 1 optional IFC skip**, an
actual Foundation v10/display run, three new actual desktop captures and
explicit remaining Windows/WSL and physical-model limitations. It also retains
an earlier rejected log-integrity incident. See the
[launch and configuration guide](STARTUP_AND_RUNTIME_RECOVERY.md) for the new
runtime discovery and selectable WSL checkout/bashrc controls. Earlier results
below remain historical evidence rather than current-head qualification.

## Verified repository baseline

- Inspected branch: `feat/doors-5pa-ceiling-downflow-demo-20261020`.
- Starting commit: `10f8721f386b2664b78df5e4ad49f1e14f4f4422`.
- Existing PR: [#1363](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/pull/1363), open when inspected.
- Fetched all remote branch refs. This execution environment has a fresh Linux
  checkout with one worktree. It cannot inspect the user's local Windows
  folders or unpushed changes and does not claim they were reconciled.
- Verified historical refs for the inspector, computed graphs, integration
  reconciliation, DesignStudio `5032284e` and New-GUI `73409bf9`. These are
  **divergent**, not ancestors of this branch. Diffs show additional inspector
  presentation and alternative OpenFOAM/VTK work. No blanket integration claim
  or automatic cross-branch replacement is justified. Those refs are preserved.
- Current branch already contains connected meshing/execution/import, native
  VTK p/U review, click seeding, frozen-field inertial particle screening,
  playback, ensemble seeding, independent trajectory diagnostics/refinement,
  iteration review, closed-door analytical comparison and Windows WSL controls.
- At the initial check, current-head OpenFOAM workflow #164 and VTK #1181
  succeeded; CI #5467 was still in progress. These are remote baseline results,
  not new local execution evidence.

## Milestone 1 — scheduled particle source backend

Implemented validated multiple sources with release start/duration/count,
enablement, optional initial velocity, exact source-bound configuration
roundtrip, cooperative cancellation, atomic runs, release-aware playback,
numerical population accounting and independently replayed JSON/CSV exports.
The existing particle force model and supported diameter/density ranges are
preserved. Invalid fluid seeds and stale/altered source metadata fail closed.

Commands executed locally:

```bash
python -m pytest -q tests/test_cfd_particles.py tests/test_cfd_particle_ensemble.py tests/test_cfd_particle_refinement.py tests/test_cfd_particle_diagnostics.py tests/test_cfd_multizone.py tests/test_cfd_multizone_results.py
# baseline: 95 passed, 0 failed, 0 skipped, 2.82 s
python -m pytest -q tests/test_cfd_particle_sources.py tests/test_cfd_particles.py tests/test_cfd_particle_ensemble.py tests/test_cfd_particle_refinement.py tests/test_cfd_particle_diagnostics.py
# milestone 1: 100 passed, 0 failed, 0 skipped, 0.36 s
```

These are synthetic numerical/API contracts. No local solver execution or
physical particle validation is inferred from them. GUI source editing and
real-field integration are subsequent milestones.

## Milestone 2 — functional source editor and 3D integration

- Added `cfd_particle_sources_gui.py`: actual Tk source table/property editor,
  create/edit/delete/enable/disable, explicit JSON save/load, worker execution,
  cancellation, stale-input/scene rejection, computed numerical population
  chart/table and independently replayed JSON/CSV exports.
- Connected the existing native VTK viewer to actual point-pick source
  creation, enabled-source glyphs and release-aware particle markers/timeline.
- Fixed a native VTK 9.3.1 X11 lifecycle defect discovered by actual repeat-open
  testing: terminate and drain the interactor registry before finalizing its
  display. Previously reopening a viewer could terminate Python. The regression
  opens, closes and reopens native windows within the same process.
- Added source contracts and actual source-editor GUI checks to VTK CI, and a
  genuine solver-field scheduled-source/export check to OpenFOAM CI.

Local validation on Python 3.12.14, real Tk 9.0.4, VTK 9.3.1 and an Xvfb display:

```bash
python -m pytest -q tests/test_cfd_particle_sources_gui.py tests/test_cfd_multizone_vtk_gui.py tests/test_cfd_particle_sources.py tests/test_cfd_particles.py -ra
# 59 passed, 0 failed, 0 skipped, 3.10 s; 36 Matplotlib deprecation warnings
bash scripts/with_openfoam10.sh python -m pytest -q tests/test_cfd_multizone_execution.py -ra
# 17 passed, 0 failed, 0 skipped, 35.55 s; actual Foundation v10 build 10-c4cf895ad8fa
```

GUI commands used an actual Xvfb TCP display wrapper because this execution
environment isolates network namespaces and does not support local X sockets.
Foundation v10 was downloaded from its official package repository and its
package SHA-256 verified before use. Runtime MPI compiler discovery emits an
`mpicc` warning in this minimal serial environment; all executed serial solver
stages completed. This does not qualify MPI/parallel execution.

The real solver test creates a fresh 13,210-cell connected mesh, runs blockMesh,
checkMesh, simpleFoam and cell-centre postProcess, and imports recorded U/p/C/phi
with original manifests/receipts. The new test injects timed numerical particles
using those actual U values and checks configuration, accounting and replayed
JSON/CSV exports. It is an execution/integration contract, not physical particle
validation or proof of convergence, closed-door performance or mesh independence.

Publication: CLI push failed with `could not read Username for 'https://github.com'`.
Milestone 1 was instead published through the authenticated GitHub connection as
`2be410a2c1e4ce31a3ca98c8db3c0f3cd482214a`. Its tree
`064ae211d10dce186b1bd0d9a09ac71e496f271f` exactly matches the tested local tree.
No force update was used. Further publication records are in the final session
report and PR #1363; a description of tests is not a claim that CI has finished.

## Milestone 3 — original mesh, usable 3D review and actual captures

- Added `cfd_multizone_mesh.py`: original VTK OpenFOAM polyMesh reader, bounded
  cell counts, exact iteration selection, full canonical report/source-hash
  agreement, recorded C matching, U/p storage-precision comparison and
  post-read receipt/integrity checks. It never reconstructs mesh topology from
  displayed cell points. VTK float32 field storage is compared with the exact
  source rounding; canonical numerical values remain unchanged.
- Added worker mesh loading, exact room/layer edge selection, field visibility
  and iso/top/front cameras in the existing VTK viewer. Hidden field points
  make interior source/particle paths inspectable. Glyph sizes are illustrative.
- Protected the existing property inspector from being squeezed to an unreadable
  strip by a wide viewport. Actual 1440×900 and 1050×680 interactions are tested.
- Replaced one legacy hover test's manual reserved `current` tag assignment
  with a genuine pointer-motion event, resolving its observed Tk 9 failure.
- Added `scripts/capture_recorded_cfd_gui.py`. It imports an existing verified
  solver case, opens the actual application/workspaces, computes scheduled
  sources and saves actual window/framebuffer pixels with per-image hashes.
  The published capture manifest records **17 images**, **zero GUI callback
  errors**, actual source iteration **100** and its **unconverged** verdict.
- Archived the original executed case, configuration, mesh, fields, solver logs
  and receipts with the numerical/source/trajectory exports. Existing older
  screenshots, reports and historical branches were preserved.

Additional executed checks:

```bash
bash scripts/with_openfoam10.sh python -m pytest -q tests/test_cfd_multizone_execution.py tests/test_cfd_multizone_mesh.py tests/test_cfd_particle_sources_gui.py -ra
# 25 passed, 0 failed, 0 skipped, 35.33 s; 22 Matplotlib warnings
python -m pytest -q tests/test_spatial_editing_gui.py tests/test_cfd_particle_sources_gui.py tests/test_cfd_multizone_vtk_gui.py tests/test_cfd_multizone_vtk.py tests/test_cfd_multizone_mesh.py -ra
# 83 passed, 0 failed, 0 skipped, 16.54 s; 40 Matplotlib warnings
cleanroomx-gui --demo --smoke
# CleanroomX GUI smoke: PASS
```

These GUI commands used the real display wrapper described above. The final
full-suite result and retained logs are in
`reports/engineering-session-20261021/REPORT.md` and `validation.json`.

## Remaining engineering work

- Closed-door leakage CFD and independently supported 5 Pa pressure control
  remain unvalidated. An analytical leakage-network comparison is a different
  model and does not establish closed-door CFD acceptance.
- The existing design-airflow result is unconverged. Numerical relaxation
  comparisons are diagnostic experiments, not evidence of physical accuracy.
- Frozen steady, one-way Stokes particle screening omits turbulent dispersion,
  Brownian motion, collision, resolved wall deposition, outlet escape
  classification and calibrated airborne concentrations.
- Physically fixed partition/equipment geometry, mesh/time-step studies and
  commissioning evidence remain necessary for engineering acceptance.
- Native Windows-to-WSL execution still requires testing on the actual Windows
  workstation. Linux execution cannot qualify that platform bridge.
- Cross-branch functional reconciliation needs dedicated review of the
  divergent GUI/OpenFOAM implementations before any merge.

Engineering release remains **HOLD**.

Final complete local suite after the CI fixture correction: **2,704 passed, 0 failed, 1 skipped**, 179.52 s, 48 Matplotlib deprecation warnings. The optional native IFC smoke is the one skip. Display/no-display checks separately produced 5 passed and 5 capability skips. Source/field/mesh tests used actual Foundation v10 and a real display.
