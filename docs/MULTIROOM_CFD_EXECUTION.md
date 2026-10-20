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
