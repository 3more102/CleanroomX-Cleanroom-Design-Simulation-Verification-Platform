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

The export also publishes a versioned `artifact_manifest.json` with SHA-256
and byte size for the JSON, dashboard, and every SVG. Outputs are staged into
a new temporary directory and published as a completed directory; the writer
refuses existing destination paths. To verify an exported bundle after copying
or archiving it, use:

    cleanroomx-cfd-pipeline two-room-analysis-audit ./two_room_analysis

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
