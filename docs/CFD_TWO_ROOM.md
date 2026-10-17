# Two-room OpenFOAM workflow

CleanroomX includes a bounded two-room case generator and an opt-in runner for
OpenFOAM Foundation v10. It is a solver-integration fixture: the example rooms,
doorway, airflow, density, and 5 Pa pressure target are synthetic. A measured
target-band result is only a diagnostic screen for those declared inputs. It is
not a facility design result or a cleanroom pressure-cascade acceptance.

## Generate and audit

The example specification is
[`cfd_two_room_5pa.example.json`](../examples/cfd_two_room_5pa.example.json).
It describes two adjacent 6 m × 4 m × 3 m rooms, a centered 0.2 m × 0.2 m
floor-level transfer opening, 0.1 m³/s supply, and a declared room 1 minus room
2 pressure target of 5 Pa with a 1 Pa tolerance. The opening is 0.22 m × 0.2 m;
the mesh is deliberately bounded to 2,304 cells.

Generate and inspect the eight manifest-bound OpenFOAM inputs:

```bash
cleanroomx-cfd-pipeline two-room-generate \
  examples/cfd_two_room_5pa.example.json ./two_room_case
cleanroomx-cfd-pipeline two-room-audit ./two_room_case
```

The generator writes 12 aligned hexahedral blocks. The doorway occupies a
shared internal face; the remaining room partition is a separate wall patch.
The audit verifies the exact input file set and SHA-256 digests. It does not
run OpenFOAM or assess the generated mesh with `checkMesh`.

## Run and inspect evidence

On Linux/WSL, install OpenFOAM Foundation v10 and source its `etc/bashrc` so
`WM_PROJECT=OpenFOAM` and `WM_PROJECT_VERSION=10`. Then run the bounded sequence
`blockMesh`, `checkMesh`, `simpleFoam`, and `foamToVTK`:

```bash
cleanroomx-cfd-pipeline two-room-run ./two_room_case \
  --receipt-directory ./two_room_receipt --timeout-seconds 900
cleanroomx-cfd-pipeline two-room-receipt-audit \
  ./two_room_receipt/two_room_run_receipt.json
```

The receipt records executable paths, stage logs and hashes, the final pressure
probe sample, solver `phi` boundary-flux diagnostics, the declared pressure
target-band screen, and hashes for every file emitted under `VTK/`. OpenFOAM's
`p` is kinematic pressure in this case, so the reported pressure difference
converts it to pascals using the density in the specification. Inlet/outlet
fluxes are measurements with no project acceptance limit; the runner does not
decide that a percentage is acceptable. Residuals are not treated as
convergence, and scientific validation remains `BLOCKED`.

If Foundation v10 or its utilities are unavailable, the runner still writes a
hash-bound incomplete receipt and exits with a nonzero status. Solver errors,
missing probes, unparseable `checkMesh` logs, or missing final-time `phi` also
leave the evidence status incomplete. The receipt's self-hash checks integrity
against accidental edits; it is not a digital signature or an authenticity
claim.

Export a completed run as a ProofGraph after checking the case, receipt, four
stage logs, pressure-probe file, final-time `phi` / mesh-boundary files used by
the flux diagnostic, and the exact `VTK/` asset set recorded in the receipt:

```bash
cleanroomx-cfd-pipeline two-room-proofgraph \
  ./two_room_case ./two_room_receipt/two_room_run_receipt.json \
  ./two-room-proofgraph.json
```

The ProofGraph reports local artifact integrity as `pass` and scientific
validation as `not_checked` / `BLOCKED`. VTK assets are checked for additions,
removals, links, and byte changes before they are included in the graph. Run
receipt schema v2 adds these VTK hashes; schema v1 receipts can still be checked
for their self-hash but must be rerun with the current runner before a
ProofGraph export. The GUI's two-room panel can generate, verify, run, preview,
and export the same evidence into the ProofGraph viewer. Hash agreement is not
authenticity because the manifest and receipt are unsigned.

## Continuous integration

The pinned Foundation v10 CFD workflow runs this case after the existing
three-grid and passive-scalar cases. It requires the pressure and flux evidence
to be present and the synthetic case's measured pressure screen to fall inside
its declared 5 ± 1 Pa band. That band checks this pinned software fixture only;
it is not a cleanroom pressure-cascade acceptance criterion. The smoke job also
exports the solver result to ProofGraph and requires the receipt-bound VTK set,
artifact-integrity `pass`, and scientific-validation `not_checked` verdicts.
Run outputs, logs, receipt, and ProofGraph are uploaded with the workflow
evidence artifact. A green workflow does not validate cleanroom performance.

Run 202 completed the four solver stages on the exact PR #1326 head and
uploaded a hash-addressed evidence archive. Its v1 receipt predates VTK asset
hash binding, so it is historical software-integration evidence; it must be
rerun with the current v2 receipt before its visualization assets can be used
in a ProofGraph integrity verdict. See the [run 202 evidence report](OPENFOAM_V10_RUN_202_TWO_ROOM_EVIDENCE.md).


## Optional receipt-bound boundary-face flow screen

The two-room diagnostic can reparse **all final-time** OpenFOAM `phi`
boundary-face values (inlet, outlet, walls, partition), recompute flux
totals, and check each reported aggregate against the existing v2 receipt.
It also computes the **sum of absolute wall and partition face fluxes**,
which cannot hide inward and outward leaks through signed cancellation.
The relative percentages below are normalized by the solver's gross inlet
volumetric flow, not by a physical measurement.

User-supplied criteria are mandatory. An example JSON file (the values are
**illustrative software inputs, not acceptable design thresholds**) is:

```json
{
  "schema_version": "cleanroomx.cfd-two-room-boundary-policy.v1",
  "max_total_boundary_imbalance_percent": 1.0,
  "max_wall_gross_leakage_percent": 1.0,
  "max_reverse_inlet_percent": 0.0,
  "max_reverse_outlet_percent": 0.0
}
```

```bash
cleanroomx-cfd-pipeline two-room-boundary-screen \
  ./two_room_case ./two_room_receipt/two_room_run_receipt.json \
  ./flow_policy.json --output ./boundary_screen.json
```

The command repeats the complete ProofGraph integrity verification,
rechecks case-bound final-time `phi` and `constant/polyMesh/boundary`
hashes, requires the same patch-face counts as the receipt, and recomputes
all relevant signed flow summaries before applying four explicit limits.
It returns `PROJECT_BOUNDARY_SCREEN_MET` (exit 0) only when the
user-defined conditions hold, `PROJECT_BOUNDARY_SCREEN_NOT_MET` (exit 3)
for a verified but out-of-limits result, and an error for invalid policy,
tampered artifacts, or inconsistent receipt calculations. The report stores
the receipt, case, `phi`, and boundary digests, plus an unsigned policy
hash and each numerical violation.

This is a **solver-derived boundary consistency screen**, not an
independent mass-flow experiment, cell-by-cell internal divergence
reconstruction, room-specific ACH, mesh-independence study, validated
convergence criterion, or physical cleanroom verification. It never
promotes `scientific_validation=BLOCKED` or
`solver_convergence=NOT_ASSESSED`.

## Optional receipt-bound numerical log screen

A complete two-room v2 receipt can be screened against **explicit, user-reviewed**
linear-solver residual and reported continuity limits. This adds no assumed
engineering acceptance threshold and does **not** establish CFD convergence or
cleanroom compliance. The screening covers **all Ux, Uy, Uz, p fields** and the
reported global continuity entries over the final specified per-field sample
window (2–100 records). It requires a terminal `End` marker and no fatal or
nonfinite solver-log marker.

Create a JSON policy with **your project's own numerical limits**, using this
exact schema (replace the illustrative values after engineering review):

```json
{
  "schema_version": "cleanroomx.cfd-two-room-numerical-criteria.v1",
  "fields": ["Ux", "Uy", "Uz", "p"],
  "max_initial_residual": 0.001,
  "max_final_residual": 0.0001,
  "max_global_continuity": 0.00001,
  "window": 3
}
```

The numbers above are formatting examples, **not recommended or validated
thresholds**. Supply a saved policy path and the specific, previously verified
case and receipt:

```bash
cleanroomx-cfd-pipeline two-room-numerical-screen \
  ./two_room_case ./two_room_receipt/two_room_run_receipt.json \
  ./criteria.json --output ./two_room_numerical_screen.json
```

The command repeats the complete ProofGraph evidence gate, then checks the
unique `simpleFoam.log` SHA-256 against the receipt before and after log
ingestion. Its result binds the receipt hash, case-manifest hash, source-log
hash and SHA-256 of the **unsigned** numerical policy. It produces
`PROJECT_NUMERICAL_SCREEN_MET` (exit code 0) only when each user-defined
log threshold passes, or `PROJECT_NUMERICAL_SCREEN_NOT_MET` (exit code 3)
for incomplete evidence or threshold violations identified within the
verified solver log. Invalid criteria, missing/tampered evidence, and other
input failures cause an error instead of a green result.

Even a passing user-supplied log screen deliberately retains
`solver_convergence=NOT_ASSESSED`, `mesh_independence=NOT_ASSESSED`, and
`scientific_validation=BLOCKED`. No independent cell-wise flux balance,
mesh refinement analysis, physical measurement comparison, or ISO acceptance
is calculated by this command. The separate numerical report is not itself
a signed source-authentication record.

## Receipt-bound CFD analysis graphs

After a completed v2 receipt has been generated, export diagnostic analysis
through the existing strict ProofGraph artifact-integrity gate:

    cleanroomx-cfd-pipeline two-room-analyze \
      ./two_room_case ./two_room_receipt/two_room_run_receipt.json \
      ./two_room_analysis

Or use **OpenFOAM workspace → Two-room pressure integration case →
Export analysis graphs…**. The GUI asks for an existing destination *parent*
directory and creates a new **cleanroomx-two-room-analysis** subdirectory.
Neither workflow overwrites the output directory or automatically launches a solver.

The result includes **analysis.json**, an **index.html** offline diagnostic
review dashboard with traceable metrics, and self-contained SVG graphs.
The dashboard also contains a per-room table of VTK volume-weighted mean
velocity, P05/P95 velocity, sampled cell count and volume, and corresponding
gauge-pressure summaries when pressure cell fields exist. Missing fields are
shown as unavailable, never substituted with values from the probes.

The export also publishes a versioned `artifact_manifest.json` with SHA-256
and byte size for the JSON, dashboard, and every SVG. Outputs are staged into
a new temporary directory and published as a completed directory; the writer
refuses existing destination paths. To verify an exported bundle after copying
or archiving it, use:

    cleanroomx-cfd-pipeline two-room-analysis-audit ./two_room_analysis

In the GUI, use **Audit saved analysis graphs…** to select an existing
analysis directory and execute this command without typing a shell command.

The independent audit checks exact file membership, SHA-256 and size, graph
names, receipt and case-manifest references, and the explicit
`scientific_validation=BLOCKED` evidence boundary. Missing, altered,
replaced, symlinked, or extra artifacts fail the audit. The bundle hash is
**not a digital signature** and does not prove source authenticity or
physical correctness.

Open the HTML file in a browser after export; it uses no remote assets or scripts.


- **simplefoam_residual_Ux.svg**, **simplefoam_residual_Uy.svg**,
  **simplefoam_residual_Uz.svg**, **simplefoam_residual_p.svg** (when logged):
  parsed initial/final per-field linear solver residuals on logarithmic axes,
  labeled by field solve count, not physical simulation time. Up to eight recorded
  fields are graphed. The JSON includes all bounded parsed residual and reported
  continuity histories; these are numerical diagnostics, not proof of convergence.
- **simplefoam_continuity_history.svg**: logged per-iteration sum-local and
  signed global continuity errors, with a zero reference line. This is an
  OpenFOAM log diagnostic, not an independently calculated mass-balance check.

- **pressure_probe_history.svg**: actual room 1 minus room 2 *point-probe*
  pressure vs OpenFOAM solver index (not physical seconds), with the declared
  *synthetic* target band.
- **inlet_outlet_flux.svg**: final solver-phi inlet/outlet patch flow in m³/s.
- **room_velocity_comparison.svg** and per-room **room_*_speed_distribution.svg**:
  volume-weighted velocity magnitude, only when a verified final-time volume VTK
  contains cell velocity U.
- **room_pressure_comparison.svg** and per-room
  **room_*_pressure_distribution.svg**: volume-weighted gauge pressure, only when
  that VTK contains scalar p, converted from kinematic pressure using the
  specified density.

Long pressure, residual, and continuity histories use bounded
extrema-preserving graph sampling (up to 1,000 vertices per plotted series).
Both first and final solver readings are kept; local minima and maxima
inside each sampling bucket are included so narrow diagnostic spikes are not
silently discarded by uniform-stride sampling. The full, unthinned bounded
numerical histories remain available in `analysis.json`. Graph sampling is
not an additional convergence or physical validation screen.

VTK graphs require the optional **vtk** Python package. Input is bounded to
256 MiB and 100,000 cells and rehashed before and after analysis. Surface VTK
datasets are excluded from room volume summaries. If no volume VTK is present,
the report labels it UNAVAILABLE and still exports pressure/flux charts;
ambiguous or malformed VTK fails rather than plotting invented values.

The JSON report records the v2 receipt hash, case-manifest hash, probe SHA-256,
VTK asset hashes, per-room volumes, percentiles and volume-weighted histogram
fractions. It does not invent an air-change rate without verifiable room-specific
flow allocation; neither temperature nor particle transport is solved by this
fixture. Probe readings are not room-average pressures and these graphs do not
establish a physical facility pressure cascade. Solver convergence stays
NOT_ASSESSED and scientific validation remains BLOCKED. Hash agreement checks
local consistency, not source authenticity or cleanroom certification.
