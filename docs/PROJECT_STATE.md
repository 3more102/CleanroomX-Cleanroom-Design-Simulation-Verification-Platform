# CleanroomX engineering state — 21 October 2026

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

## Engineering limitations and next priorities

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
