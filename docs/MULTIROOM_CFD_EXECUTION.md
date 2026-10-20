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
- Section views display computed cell values and vectors. Click a coloured
  recorded fluid cell in **Computed sections** to seed a bounded 3D *steady
  streamline*. The gold line is an **XY/XZ/YZ projection of the 3D trace** and
  is NOT restricted to the selected section plane. Switch planes to inspect
  alternative projections. Up to 20 traces can be displayed; **Clear traces**
  resets them. **Export 3D traces** writes an exclusive-create JSON file with
  the selected iteration, recorded run/manifest hashes, units and 3D paths.
  Seed points always come from actual recorded cell centres.
- Trace integration uses the recorded cell-centred `U` velocity for the
  selected SIMPLE iteration, represented piecewise constantly, and limited-step
  second-order midpoint marching. Each segment checks occupied fluid voxels;
  it terminates rather than jumping through missing wall/partition voxels.
  `max_integration_s` is only a streamline integration parameter for a steady
  field; this is NOT transient solver time or measured particle travel time.
- The line does NOT model Brownian motion, turbulence dispersion, particle
  inertia, wall deposition, resuspension or particle injection. Working-plane
  UDAF acceptance criteria, true VTK 3D streamline rendering/clipping, mesh
  convergence and validated recirculation topology remain unimplemented.
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


## Computed steady-streamline interaction (20 October 2026)

The new `cleanroomx.cfd_streamlines` helper accepts only a nonempty
`cleanroomx.multizone-results.v1` report with cell-centred `U` and
`voxel_pitch_m`; it preserves recorded case- and run-receipt SHA-256 identifiers
in the trace object. It does not load unverified arbitrary velocity screenshots.

```python
from cleanroomx.cfd_multizone_results import analyze_multizone_case
from cleanroomx.cfd_streamlines import trace_computed_streamline

report = analyze_multizone_case(
    "/tmp/cx-open-case", density_kg_m3=1.2, reference_room_id="corridor"
)
seed = report["cells"][0]["center_m"]  # actual solved-fluid cell centre
trace = trace_computed_streamline(report, seed, max_integration_s=20)
print(trace["termination"], len(trace["points"]))
```

The `points` array includes 3D coordinates, source room, locally recorded
speed, and integration parameter. Stops are explicitly labelled
`domain_exit`, `stagnation`, `max_steps` or
`max_integration_parameter`. None imply engineering acceptance. Synthetic
unit fixtures in `test_cfd_streamlines.py` test numerical boundary behavior
only; the separate `test_cfd_multizone_execution.py` checks tracing on
actual OpenFOAM fields when Foundation v10 is available.


## Native interactive VTK 3D review (20 October 2026)

The **Open real VTK 3D** control in the *Computed sections* tab opens
an interactive window after a successful import of recorded CFD fields.
When the installed VTK wheel does not contain `libvtkRenderingTk`, CleanroomX
opens a separate native VTK graphics window and keeps its controls in Tk. This
fallback deliberately avoids declaring missing VTK/Tk embedding support a
solver error.
Install optional dependencies (`python -m pip install -e ".[cfd]"`) and
launch the CleanroomX desktop in the graphical Linux environment in which
the recorded OpenFOAM Foundation v10 case is accessible. Mouse drag rotates,
scroll zooms, and Shift-drag pans. The 3D window supports:
- **speed / pressure** live switching. Colored 3D points map actual cell
  centers and actual recorded `U` magnitude or density-converted pressure
  relative to the explicitly selected reporting reference.
- **Display sampled U direction arrows** toggles 3D glyphs derived from
  solver velocity vectors. Glyph lengths are scaled for readability and are
  **not** travel distances.
- **Gold lines** show bounded 3D steady streamlines already seeded from
  computed cells in the 2D tab. Switching from the 2D projection does not
  create particle transport or transient timesteps.
- **Room wireframes** represent input design bounds and are not extracted
  pressure isosurfaces, approved CAD partitions or certified flow geometry.

The VTK view is a spatial visualization of the recorded solved-cell samples;
it does **not** reconstruct a continuous volume field between cell centers.
No certification, cleanroom pressure cascade, particle tracking or convergence
is inferred from successful display. VTK field / geometry smoke tests are
included in the dedicated `CFD VTK Regression` workflow.


## Actual-cell 3D room and plane selection (20 October 2026)

The native/embedded VTK control panel now offers `Room` (`all` or a room ID
that exists in the *recorded CFD cells*), `Plane` (`all`, `x`, `y`, `z`),
`Coordinate (m)` and **Apply room/plane**. Combined selections show exactly
the solved cell centres belonging to the selected room and layer. At most one
recorded lattice layer is selected at each plane coordinate, using a strict
half-voxel criterion; no gaps, inferred intermediate values or interpolation
are added. The matching velocity-vector glyphs use the same selection.
The input room outline remains a *design* wireframe. Previously imported 3D
steady streamline geometry remains visible across a plane selection to show
its full spatial route, and is not claimed to lie within the plane.

An out-of-range/nonfinite plane, unmodeled room or zero-cell intersection is
rejected before replacing the existing scene; the operator receives a status
message rather than a fabricated blank/filled plane. Camera position is retained
on valid scene changes. Displayed numerical convergence status is taken from the
recorded selected iteration (not from the VTK renderer). These capabilities
do not create CFD calculations, pressure control, particle transport or
validated physical results. Unit tests use expressly artificial sample values,
and GUI tests exercise the native VTK window under a real Xvfb display.


## 3D click-to-seed recorded-field streamlines (20 October 2026)

In **Open real VTK 3D** enable **Pick fluid seed in 3D** and click
directly on a visible colored computed cell centre. A vtkPointPicker
restricted to the recorded CFD point actor selects an actual solved-fluid
cell, never a room wireframe, vector arrow, wall, free-space location,
or synthetic interpolated sample. Room and plane filtering affect which
cells are selectable. Existing paths remain visible as whole 3D routes.

The selected cell's *recorded* coordinates seed a bounded steady-streamline
integration using the same OpenFOAM cell-centred U values and source iteration.
The implementation refuses stale/mixed-source traces, missing/invalid fluid
cells and more than 20 paths. Clicking off the real field displays a clear
rejection message; **Clear 3D traces** removes only paths in the 3D viewer. **Export 3D traces** writes a provenance-tagged JSON collection containing
the selected OpenFOAM iteration, manifest/receipt SHA-256 identifiers, source
units and all currently displayed 3D streamline coordinates. Existing files
are never overwritten; a failed export is reported in the GUI status.
Rotation/zoom retain the existing VTK camera and the selected fluid scene.
The 3D control status labels each new path's point count and termination
reason. Colors/room shapes remain a review visualization only.

**Physics limitation:** These are *streamlines* from a recorded steady U
field, not transient Lagrangian particle tracking. They do not include
particle diameter, inertia, Brownian diffusion, gravity, deposition,
collisions or a solved transient particle concentration field. Unit cases
are synthetic and only the dedicated OpenFOAM execution job provides
solver-derived CFD provenance checks.


## Physics-parameterized one-way particle screening (20 October 2026)

**Scope:** This phase adds the independent `cfd_particles.py` particle
trajectory *screening* integrator and a separate **One-way particle screening**
mode in **Open real VTK 3D**. A user can select particle diameter (0.5–20 μm),
material density (100–20000 kg/m³), elapsed integration duration (up to 60 s)
and a computed CFD fluid-cell injection point. **Pick fluid seed in 3D** must
be enabled; choose the particle mode before clicking a colored cell-centre.
Particle paths are **green**, distinct from the **gold** steady air streamlines.

The particle model solves the one-way, low-slip-Reynolds Stokes drag equation
with a fixed-air Cunningham correction, finite particle velocity relaxation,
buoyancy-adjusted gravitational settling (default -z), and exact constant-U
relaxation within a short time step. Each fluid cell's U is a *recorded*
OpenFOAM field value. The gas field is held **frozen** at the selected
OpenFOAM SIMPLE iteration and sampled as piecewise constant cell-centred U;
the integrator does **not** run a new OpenFOAM solver or interpolate missing
cells. Steps are bounded by local cell pitch and integration duration. Paths
stop at solid/outside-fluid boundaries without inventing rebound or
deposition. A slip Reynolds number >=1 raises an explicit Stokes-regime
validity warning, not a confident conclusion.

The particle path's `elapsed_particle_s` is *model integration time in a
frozen gas field*, **not** an actual transient OpenFOAM solver time. Separate
**Clear particles** and **Export particle paths** controls export a
no-overwrite provenance-tagged JSON containing CFD iteration and source SHA-256
receipts. This is a deterministic screening model, **not CFD-coupled
validated particle transport**: no turbulence-induced stochastic dispersion,
Brownian diffusion, agglomeration, electrostatic forces, wall trapping,
deposition, resuspension, collisions, transient gas fields or two-way
feedback are modeled. No infection/contamination or cleanroom compliance
claim is made. The test suite explicitly distinguishes synthetic numerical
fixtures from real OpenFOAM cell-field ingestion checks.


### Recorded-vertex particle playback

The **Particle elapsed time (s)** slider and **Play samples / Pause**
buttons in the native VTK 3D window show bright green particle-position markers.
Every marker uses the most recent **actual numeric integration vertex** at or
before the selected elapsed particle-model time. Playback holds positions
between solver-screening integration samples rather than interpolating
fictitious particle positions. The green path remains visible to review the
full one-way particle trajectory; the gold path is a separate steady-air
streamline. Playback speed is an operator display setting, *not* OpenFOAM
physical time nor a CFD-transient video. If a simulated particle reaches an
unsolved or solid voxel boundary, its screening path terminates rather than
claiming deposition. The native VTK + real Tk + Xvfb smoke regression exercises
the time slider and verifies that marker coordinates equal recorded sample
positions from the frozen-field particle model.


## Engineering review: measured open-door delta versus 5 Pa design target

The **Engineering review** tab and the exported `engineering-review.json`
show per-door pressure differences computed from the *recorded* OpenFOAM
room-mean kinematic pressure, converted to Pa using the explicitly selected
air density. A signed **Computed − design** difference is reported instead
of assuming the designer's target was achieved. The table also displays the
actual `phi`-integrated forward and reverse volume-flux components (m³/h).
The results remain tied to the source run receipt, manifest SHA-256 and
selected SIMPLE iteration.

The engineering outcome is **HOLD** for this *all-doors-open* scenario even
if the computed differences happen to equal 5 Pa or OpenFOAM reports
numerical convergence. It is impossible to demonstrate a *closed-door*
pressure cascade from an open-door simulation. Reviewer-defined compliance
tolerances are deliberately **not** invented. The tab separately surfaces
selected-iteration numerical convergence, opposing pressure direction,
missing design targets and absence of evidence for closed-door leakage,
pressure control, physical validation and mesh sensitivity. Such findings
are observations and investigation priorities, not automatic prescriptions
to increase FFU speed or change supply/return openings.

The standalone `engineering-review.json` can be exported from the GUI
without overwriting existing records. The ordinary **Export report** action
also saves `engineering-review.json` alongside its other computed evidence
and includes a visibly noncertifying door comparison in the HTML dashboard.
A completed OpenFOAM execution plus output/manifest hash checks establish
field *provenance*, not commissioning acceptance or cleanroom performance.
