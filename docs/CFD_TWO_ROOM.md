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
2 pressure target of 5 Pa with a 1 Pa tolerance. The mesh is deliberately
bounded to 2,304 cells.

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
probe sample, solver `phi` boundary-flux diagnostics, and the declared pressure
target-band screen. OpenFOAM's `p` is kinematic pressure in this case, so the
reported pressure difference converts it to pascals using the density in the
specification. Inlet/outlet fluxes are measurements with no project acceptance
limit; the runner does not decide that a percentage is acceptable. Residuals
are not treated as convergence, and scientific validation remains `BLOCKED`.

If Foundation v10 or its utilities are unavailable, the runner still writes a
hash-bound incomplete receipt and exits with a nonzero status. Solver errors,
missing probes, unparseable `checkMesh` logs, or missing final-time `phi` also
leave the evidence status incomplete. The receipt's self-hash checks integrity
against accidental edits; it is not a digital signature or an authenticity
claim.

Export a completed run as a ProofGraph after checking the case, receipt, four
stage logs, pressure-probe file, and final-time `phi` / mesh-boundary files used
by the flux diagnostic:

```bash
cleanroomx-cfd-pipeline two-room-proofgraph \
  ./two_room_case ./two_room_receipt/two_room_run_receipt.json \
  ./two-room-proofgraph.json
```

The ProofGraph reports local artifact integrity as `pass` and scientific
validation as `not_checked` / `BLOCKED`. The GUI's two-room panel can generate,
verify, run, preview, and export the same evidence into the ProofGraph viewer.
Hash agreement is not authenticity because the manifest and receipt are
unsigned.

## Continuous integration

The pinned Foundation v10 CFD workflow runs this case after the existing
three-grid and passive-scalar cases. It requires the solver-backed pressure and
flux evidence to be present, but does not require the synthetic case to meet
the declared 5 Pa target. Run outputs, logs, and receipt are uploaded with the
workflow evidence artifact. A green workflow means that the software path and
evidence parsing completed; it does not validate cleanroom performance.
