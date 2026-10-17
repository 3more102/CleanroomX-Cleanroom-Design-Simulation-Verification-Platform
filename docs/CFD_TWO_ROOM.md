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
