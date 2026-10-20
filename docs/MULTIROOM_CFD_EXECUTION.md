# Multiroom CFD execution and computed-field review

The connected **all-doors-open** model now runs with OpenFOAM Foundation v10.
It is an isothermal, steady laminar screening model. Execution does not establish
numerical convergence, a valid laminar flow regime, UDAF compliance or certification.

## Desktop workflow

1. Install this branch (`python -m pip install -e .`). In Linux, source the
   actual Foundation v10 environment before starting `cleanroomx-gui --demo`.
2. Use the existing 2D/3D design workspace to inspect room geometry. Select a door
   and use **Toggle door** or edit **Door state**. Changes support undo/redo and
   save/reopen. Separate FFU and return visibility controls affect depiction only.
3. Save the project. **Analyze → Generate Connected Open-Door CFD Case** explicitly
   generates a hypothetical scenario with every connecting door open, regardless
   of the saved design leaf states. Those original states remain in the manifest.
4. **Analyze → Run / Review Multiroom CFD** opens the execution workspace. Select
   the generated folder and run OpenFOAM. The process uses the inherited Linux
   environment. Review the live stage logs.
5. Enter the actual air density in kg/m³ and choose a modeled reference room ID
   (the demo uses `corridor`). Import recorded computed fields. Pressure in Pa is
   `density × (kinematic pressure − computed reference-room mean)`.
6. Review room/door tables, pressure bars, actual cell sections and projected
   velocity vectors, saved SIMPLE iterations, residual histories, mesh quality
   and provenance. Export a new report folder containing HTML, JSON, full cell
   CSV and residual CSV. **NOT CONVERGED** stays visible when appropriate.

Native Windows-to-WSL process launching has not been implemented or verified.
The existing Windows launcher and independent-room exporter remain available;
run this workflow within a sourced Foundation v10 Linux/WSL environment. A native
Windows GUI does not automatically acquire WSL solver executables.

## Reproduce the executed scenario

The viscosity and density below are explicitly selected example air properties,
not measurements of a facility. Room supply inputs come from the saved project.

```bash
source /opt/openfoam10/etc/bashrc
cleanroomx-cfd-pipeline multizone-generate examples/gui_demo.cleanroomx.json /tmp/cx-open-case \
  --door-mode open --kinematic-viscosity-m2-s 1.5e-5 \
  --max-iterations 600 --output-interval 50
cleanroomx-cfd-pipeline multizone-run /tmp/cx-open-case
cleanroomx-cfd-pipeline multizone-analyze /tmp/cx-open-case \
  --density-kg-m3 1.2 --reference-room-id corridor \
  --report-directory /tmp/cx-open-report
```

The runner checks the Foundation v10 identity and hashes all generated inputs.
It records commands, executable locations, runtime build, timestamps, durations,
exit codes, timeouts, log hashes and computed output hashes in `run-receipt.json`.
It refuses an existing run or stale nonzero-time fields. Failed `checkMesh`, fatal
diagnostics and incomplete stage logs prevent a successful receipt. The importer
checks recorded inputs, outputs and logs before reading real `p`, `U`, `C` and
surface flux `phi`. Door fluxes use owner/neighbour addressing, not guessed
cell-velocity integration. These receipts detect accidental changes; they are
not signed third-party attestations.

## Actual 600-iteration local execution

See `reports/multiroom-cfd-20261020/` for the actual input manifest, execution
receipt, four losslessly compressed `.log.gz` logs, computed summary and desktop screenshots. Full field files
are not committed; regenerate them using the commands above. The report retains
their execution hashes. Software/environment changes can alter numerical output;
do not expect the runtime/path-dependent log hashes to repeat.

- 13,210 equal-volume hexahedra; one connected region; `Mesh OK`.
- Three 1.0 × 2.1 m open apertures, each with 70 real internal connecting faces.
- 12 ceiling FFUs and three low-return devices have resolved mesh faces.
- All four execution stages finished; **SIMPLE did not report convergence**.
- Computed adjacent mean pressure differences: Process→Preparation ≈ 0.03023 Pa;
  Preparation→Ante ≈ 0.003136 Pa; Ante→Corridor ≈ −0.003860 Pa.
- These provisional open-door outputs do **not** achieve or validate the 5 Pa
  closed-door design targets. Return patches use zero gauge kinematic pressure;
  the corridor reference is a reporting normalization, not an added boundary.

## Remaining engineering limits

- Closed-door leakage is not coupled CFD. An impermeable door is not a leakage
  model. The original separate-room exporter remains available for closed doors
  and rejects saved open leaves instead of silently treating them as walls.
- Partitions occupy one owner-side voxel layer. Thickness changes with mesh
  pitch; a physically fixed partition/undercut model is needed before a meaningful
  mesh-independence study. Multiple doors on the same room pair are rejected.
- FFU/grille footprints are sampled by face centres. No manufacturer flow curve,
  leakage coefficient, pressure control, turbulence validation or commissioning
  evidence is inferred. The corridor has no FFU/return patch; its unrelated
  verification-analysis supply input is not applied to this connected case.
- Section views display computed cell values and vectors. Computed 3D
  streamlines, working-plane UDAF acceptance criteria, clipping of computed 3D
  fields and validated recirculation classification remain unimplemented.
- Upward-volume fraction and whole-room downward-velocity CV are descriptive
  diagnostics. They are not a recirculation topology test or cleanroom compliance.

## Verification

`tests/test_cfd_multizone_execution.py` executes actual Foundation v10 tools and
tests ingestion, units, pressure reference, face-flux balances, provenance,
altered-output rejection, a real solver dictionary failure and real Tk widgets.
A separate timeout-injection test is explicitly a failure-contract test, not
solver evidence. Without Foundation v10 these tests skip; with
`CLEANROOMX_REQUIRE_OPENFOAM=1` a missing runtime fails the test. The dedicated
`OpenFOAM Multiroom Execution` workflow installs the official Foundation package
and enables that requirement. The ordinary CI and VTK regression gates remain.

Local validation for this milestone: standard full suite **2,342 passed,
91 skipped** (display/native BIM prerequisites); all GUI modules under a real
virtual display **175 passed, 0 failed, 0 skipped**; focused actual OpenFOAM,
computed-field/Tk, door and independent-export checks **95 passed, 0 failed,
0 skipped**. The GUI audit also corrected the fit-selected return contract and
a ProofGraph tree-selection event loop; existing GUI fixtures were brought into
line with the retained-context search, revision identity and smoke-run APIs.
The final complete suite with both Foundation v10 and a real Tk display passed
**2,432 tests, 0 failed, 1 skipped** (optional native IfcOpenShell dependency).

Foundation references: [v10 installation](https://openfoam.org/download/10-ubuntu/)
and [momentumTransport dictionary](https://doc.cfd.direct/openfoam/user-guide-v10/turbulence).

## Numerical review follow-up (20 October 2026)

The **Residual histories** tab now lists the selected iteration's first initial
residual, last linear-solver final residual and configured initial-residual
limit for p/Ux/Uy/Uz. A white cursor marks the selected saved fields on the full
run history. The run's eventual convergence verdict is reported separately.
Selecting an earlier iteration cannot inherit a later SIMPLE convergence flag.
Small final linear residuals alone cannot produce a convergence verdict.

The room table includes the absolute net flow imbalance as a percentage of
mean incoming/outgoing flow. Every computed `phi` contributes with its actual
owner/neighbour sign. In addition to room net balances, the importer sums
absolute cell flow imbalances and reports the largest cell imbalance. This
avoids hiding local continuity errors behind cancellation in the global net.
These metrics have units of m³/s; no commissioning tolerance is assumed. The
OpenFOAM log's continuity diagnostics are retained separately, without
reinterpreting their units as volumetric flow.

HTML/JSON reports include these diagnostics. `room-balances.csv` exports room
incoming/outgoing flow, net imbalance, relative imbalance and cell-balance
statistics. `residuals.csv` retains the complete run history; `numerics` in the
JSON identifies the exact selected iteration and full run convergence iteration.

The actual numerical regression reduces the demo's supply inputs by **1/1000**
(Process 2.7, Preparation 1.2, Ante 0.72 m³/h), retaining the geometry and explicit
air-property assumptions. This deliberately reduced-flow case tests the
convergence/snapshot contract. It is not evidence for the design airflow,
closed-door leakage, cleanroom performance or a 5 Pa cascade. On the local
Foundation v10 runtime it converged at iteration **163**; its saved iteration
50 remains unconverged in both the API and the real Tk review panel.

Actual manifests, execution receipts, losslessly compressed logs, computed
summaries and real Tk screenshots are in `reports/multiroom-numerics-20261020/`.
The low-flow input project is retained there; complete output fields can be
regenerated with `multizone-generate` using 400 iterations and output interval
50. Runtime-dependent hashes and convergence iteration can vary by environment.
The ordinary design-airflow 600-iteration scenario is retained separately.

The dedicated OpenFOAM workflow now uses `scripts/with_openfoam10.sh`.
Foundation v10's optional interactive startup probes can exit a `bash -e`
shell before pytest starts. The wrapper temporarily disables errexit for that
initialization, restores fail-fast behavior, verifies all four executables and
the actual Foundation v10 identity, then executes the requested command. A
missing or unusable runtime still fails. For example, from the repository:

```bash
bash scripts/with_openfoam10.sh cleanroomx-gui --demo
bash scripts/with_openfoam10.sh xvfb-run -a python -m pytest -q \
  tests/test_cfd_multizone_execution.py tests/test_cfd_multizone_results.py
```

The startup correction passed the dedicated GitHub workflow (run 3); new
convergence and conservation checks passed locally with actual Foundation v10
and real Tk widgets. Parser-only synthetic fixtures are explicitly separated
from the actual solver executions.

The full GUI regression also exposed toolbar overflow at 1050×680: the added
FFU/return/door controls could hide **Validate**. Those controls and validation
now occupy a separate compact row. All 57 spatial editing GUI checks passed
after the correction, including both supported test window sizes.
Resizing also protects workspace height against an oversized output pane;
the minimum-size check requires the design body itself to remain visible.
All GUI modules plus spatial editing passed **232 checks** with real Tk 8.6
after this resizing correction.
The final complete suite with actual Foundation v10 and real Tk 8.6 passed
**2,439 tests, 0 failed, 1 skipped** (optional native IfcOpenShell) in 160.20 s.
The exact log, source hashes and validation summary are retained in the new
report folder as `full-suite.log` and `validation.json`.
