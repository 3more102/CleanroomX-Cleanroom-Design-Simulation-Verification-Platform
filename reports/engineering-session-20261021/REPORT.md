# CleanroomX engineering execution report — 21 October 2026

## A. Repository and publication

Continued the existing branch
`feat/doors-5pa-ceiling-downflow-demo-20261020` and open
[PR #1363](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/pull/1363).
Baseline: `10f8721f386b2664b78df5e4ad49f1e14f4f4422`.

Published milestones:

| Commit | Result |
|---|---|
| `2be410a2c1e4ce31a3ca98c8db3c0f3cd482214a` | Validated scheduled-source backend and accounting |
| `8dee780a71f262522e664c1f2655f0fc3656f7d9` | Real source editor, 3D picking/playback and VTK repeat-open repair |
| `15c7b619dcba5fcc56f4048bfc57e647d506c417` | Correct headless GUI test capability handling |

The original-mesh, camera/visibility, inspector and complete evidence milestone
includes this report; its final commit is recorded on the PR and in the session
response. No merge, force push or branch deletion was performed. CLI push failed
with `could not read Username for 'https://github.com'`; publication uses the
authenticated GitHub connection with expected-head, non-force ref updates.
Published source blobs and tree identities are checked against the tested local
files before moving the branch.

The clone contains 1,689 remote branches plus the symbolic origin/HEAD ref.
Historical inspector, graph, DesignStudio and New-GUI refs were verified and
compared; they remain divergent. A fresh Linux checkout cannot certify the
user's Windows worktrees or unpushed changes. No broad consolidation was claimed.

## B. Implementation and integration

- Added `cfd_particle_sources.py`: validated fluid seeds, source IDs, enabled
  flags, count/start/duration, initial velocity, deterministic release schedule,
  common observation horizon, atomic cancellable integration, numerical
  population ledger, provenance-bound source save/load and replayed exports.
- Added `cfd_particle_sources_gui.py`: actual saved-source table/property editor,
  create/edit/delete/enable/disable, source JSON persistence, background numerical
  work, stale-input/scene rejection, population chart/table and JSON/CSV export.
- Reused the existing frozen-U inertial Stokes/Cunningham kernel. Release-aware
  playback uses actual recorded samples; it hides particles before release and
  holds the terminal sample after numerical termination.
- Extended `cfd_multizone_vtk.py` with clicked source placement, source glyphs,
  release-aware timeline, field visibility, camera presets and original mesh.
  Native VTK 9.3 X11 now drains its terminated interactor before display
  finalization, fixing observed process termination on viewer reopening.
- Added `cfd_multizone_mesh.py`: reads original polyMesh topology, matches the
  exact selected report, original C and U/p, supports exact room/layer cell
  selection and rejects stale/damaged source files. VTK float32 fields are
  checked against exact source-to-float32 conversion; canonical p/U do not change.
- Protected `spatial.py`'s property inspector against viewport-induced collapse.
  Updated the legacy hover test to generate an actual native pointer event.
- Extended real OpenFOAM and VTK CI coverage. Fixed a newly introduced GUI test
  fixture that failed the general no-display CI job; both headless behavior and
  real-display execution are checked separately.

## C. Actual CFD execution and numerical evidence

The archived case was generated from the existing bundled project in explicit
**all-doors-open** mode and executed with Foundation v10 build `10-c4cf895ad8fa`.
blockMesh, checkMesh, simpleFoam and postProcess completed with recorded commands,
return codes, logs and hashes. Saved SIMPLE iterations: 25, 50, 75 and 100.
All p/U/C/phi import checks and original mesh integrity checks passed.

| Recorded quantity | Value |
|---|---:|
| Cells / connected regions | 13,210 / 1 |
| checkMesh verdict | Mesh OK |
| Cell volume, min = max | 0.015 m³ |
| Mesh fluid volume | 198.15 m³ |
| Maximum aspect ratio | 5 |
| Maximum nonorthogonality | 0° |
| Maximum skewness | 2.962039982×10⁻¹⁴ |
| Signed boundary imbalance | 0.00019443222 m³/s |
| Relative boundary imbalance | 0.00015149415 |
| Sum of absolute cell flow imbalances | 0.03123410089 m³/s |
| Maximum absolute cell imbalance | 0.0000588494076 m³/s |
| Selected iteration solver convergence | **False** |

No acceptance tolerance is inferred from these values. A successfully executed
run is distinct from a converged or physically validated simulation. This
100-iteration design-flow run remains unconverged; neither this case nor the
pre-existing 600-iteration result demonstrates a closed-door 5 Pa cascade.

Two sources and eight scheduled numerical particles were integrated from the
actual recorded velocity field. Boundary termination remains **unresolved**,
not escape or deposition. Numerical accounting and exact replay passed. Air
properties, gravity, particle size/density, release clock and trajectory ages
are recorded; particle age and source release time are not SIMPLE iteration time.

## D. Actual GUI and screenshots

`cleanroomx-gui --demo --smoke` returned **PASS**. Interactive checks exercised
source CRUD/persistence, actual VTK point picking, worker responsiveness,
cancellation, stale-scene rejection, population graphs, scheduled markers,
exports, camera/field controls, mesh loading/selection and repeat-open cleanup.
The inspector was exercised at 1440×900 and 1050×680.

[17 genuine captures](../../docs/real-gui-screenshots-20261021/README.md) show
main/start workspace, design studio, multiroom geometry, property inspector,
CFD review, original mesh, computed velocity section, pressure/airflow analysis,
source editor, computed particle paths, residuals, iteration analysis,
population, 3D controls, 3D p/U and a camera close-up. Native window/framebuffer
pixels were captured; no screenshot was manufactured. The capture run recorded
**zero GUI callback errors**. Per-image hashes are in `capture-manifest.json`.

## E. Executed validation

| Executed scope | Passed | Failed | Skipped | Elapsed |
|---|---:|---:|---:|---:|
| Complete suite with real solver and display | 2,704 | 0 | 1 | 179.52 s |
| Initial particle core | 100 | 0 | 0 | 0.36 s |
| Source/VTK GUI + core | 59 | 0 | 0 | 3.10 s |
| Actual solver, mesh and source GUI | 25 | 0 | 0 | 35.33 s |
| Final spatial, source and VTK GUI/mesh | 83 | 0 | 0 | 16.54 s |
| CI fixture with actual display | 5 | 0 | 0 | 2.25 s |
| CI fixture without a display | 0 | 0 | 5 | 0.10 s |

Final full run emitted 48 Matplotlib deprecation warnings. The five deliberate no-display skips are a separate capability check; the real-display suite executes those tests.


The complete suite used actual Foundation v10, Python 3.12.14, Tk 9.0.4,
VTK 9.3.1 and an actual Xvfb display. The single local optional IFC skip is
reported explicitly. Matplotlib emitted deprecation warnings; they are not
solver errors. MPI compiler discovery emits an `mpicc` warning in the minimal
serial runtime; parallel/MPI execution was not qualified.

Core full-suite command, inside the actual display wrapper:

```bash
bash scripts/with_openfoam10.sh python -m pytest -q -ra
```

The exact execution-specific wrapper and retained command output are in
`validation-logs/`. A conventional Linux/WSL reproduction uses
`bash scripts/with_openfoam10.sh xvfb-run -a python -m pytest -q -ra`.
The wrapper exists because this execution environment isolates network
namespaces and disallows local X sockets, not because Tk interaction was mocked.

Remote milestone `8dee780a` VTK workflow #1185 and real OpenFOAM workflow #166
succeeded. Its general CI #5469 failed on the missing-display fixture; repair
`15c7b619` was published. Current-head checks must be read independently; a local
pass does not imply remote CI has completed or that Windows WSL execution works.

Synthetic analytical/unit fixtures are identified in tests. They are not solver
evidence, and overlapping focused test totals must not be added together.

## F. Remaining engineering work

1. Resolve design-flow numerical convergence and establish physically justified
   laminar/turbulent assumptions before accepting airflow predictions.
2. Model actual closed-door leakage/control using independently supported
   geometry and operating inputs; the analytical leakage network remains a
   different model. Validate the pressure cascade separately.
3. Establish fixed physical partition/equipment geometry, mesh independence and
   appropriate spatial/temporal particle convergence studies.
4. Resolve outlet/wall intersections and validate escape, deposition, turbulent
   dispersion and other relevant particle physics. Current frozen-U screening
   cannot supply validated concentration, exposure or cleanroom class.
5. Verify the native Windows-to-WSL bridge on the actual workstation; Linux
   serial success and Windows launcher parsing do not qualify it.
6. Review divergent graph/inspector/OpenFOAM branch work before consolidation;
   preserve their independent features. Integrate source definitions into the
   canonical project schema only with a deliberate versioned migration.
7. Expand beyond the bounded 20-particle screening workflow after numerical and
   performance qualification. No production-scale aerosol transport is claimed.

Engineering release: **HOLD**.

## Reproduction artifacts

- `reproduction-case.tar.gz`: actual case inputs, mesh, saved fields, logs and
  receipt. Extract into a new directory; the original receipt should be preserved.
- `manifest.json`, `run-receipt.json`, compressed stage logs and
  `computed-report/`: original execution identity and computed engineering data.
- `particle-sources.json`, `particle-run.json`, `particle-trajectories.csv`:
  source definitions, modeled samples and independently replayed exports.
- `source-sha256.json`, `validation.json`, `capture-manifest.json`,
  `artifact-sha256.json`: source, tests, genuine captures and artifact identity.
