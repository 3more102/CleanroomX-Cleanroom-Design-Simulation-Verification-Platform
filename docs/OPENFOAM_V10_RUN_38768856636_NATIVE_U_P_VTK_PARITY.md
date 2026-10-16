# OpenFOAM Foundation v10 run 61: native U/p to VTK parity

## Run and scope

- GitHub Actions run [38768856636](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38768856636) completed successfully on implementation commit `9225d28e22bada1b913de68f30fb76410e513fa2`.
- Runtime: OpenFOAM Foundation v10 build `10-c4cf895ad8fa`.
- The nine synthetic cases completed all 36 command stages: `blockMesh`, `checkMesh`, `simpleFoam`, and `foamToVTK` for each case. Each solver run reached 150 s. The export selected final-time `U` and `p` with ASCII polyhedral output and disabled point values.
- Exact-head CI [38768856509](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38768856509) and CFD VTK Regression [38768857050](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38768857050) passed.
- Evidence artifact: [11989364311](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38768856636/artifacts/11989364311), archive SHA-256 `fd348a923c6f46b8d656700c029bfdce13187a8eeb7d2f5a6926581a02bd05ba`.

The workflow compared native final-time OpenFOAM cell fields to their exported VTK cell arrays through a complete, unique `cellID` mapping. It did not infer cell correspondence from VTK array order. All 47,304 cells were checked for each field: 141,912 velocity components and 47,304 kinematic-pressure values. VTK stores both fields as `float`; the recorded bound accounts for binary32 conversion and the six-significant-digit ASCII output.

## Per-case parity

| Case | Cells | U max absolute error (m/s) | U serialization bound (m/s) | p max absolute error (m²/s²) | p serialization bound (m²/s²) |
|---|---:|---:|---:|---:|---:|
| configuration_1/coarse | 216 | 4.91466e-7 | 5.14901e-7 | 2.32696e-8 | 5.09313e-8 |
| configuration_1/medium | 1,728 | 5.07119e-7 | 5.14901e-7 | 4.93825e-8 | 5.18626e-8 |
| configuration_1/fine | 13,824 | 5.12711e-7 | 5.14901e-7 | 5.06463e-8 | 5.18626e-8 |
| configuration_2/coarse | 216 | 5.28882e-8 | 5.74506e-8 | 4.99452e-9 | 5.46566e-9 |
| configuration_2/medium | 1,728 | 5.53792e-8 | 5.74506e-8 | 5.05525e-9 | 5.46566e-9 |
| configuration_2/fine | 13,824 | 5.57160e-8 | 5.74506e-8 | 5.06214e-9 | 5.23283e-9 |
| configuration_3/coarse | 216 | 5.06186e-8 | 5.74506e-8 | 5.01345e-9 | 5.23283e-9 |
| configuration_3/medium | 1,728 | 5.56442e-8 | 5.74506e-8 | 5.01948e-9 | 5.23283e-9 |
| configuration_3/fine | 13,824 | 5.58777e-8 | 5.74506e-8 | 5.00528e-9 | 5.23283e-9 |

All nine U and all nine p parity records passed their stated serialization bounds. Worst-case absolute errors were `5.12711003126e-7 m/s` for U and `5.06462887948e-8 m²/s²` for p. These bounds describe file conversion only; they are not solver tolerances.

After downloading the artifact, I independently verified its archive digest, the native U/p and VTK file digests, all four command-log digests per case, and the manifest cell counts. Re-running both CleanroomX parity audits on all nine archived cases reproduced the workflow's parity records exactly.

## Diagnostic limits

This remains synthetic execution evidence. The workflow's triage status is `DIAGNOSTIC_ONLY`, and scientific validation is `BLOCKED`. All 18 terminal log-based U/p residual screens remain above their configured tolerances. The final-time flux report measures all nine cases, but its acceptance criterion is `NOT_SET`; the reported imbalances range from 0.005341% to 0.187145%. This run does not establish physical correctness, mesh independence, GCI eligibility, or measured cleanroom correlation. Issue #1296 remains open.

The VTK capability rows therefore remain `partial`. This run extends verified final-time field parity to U and kinematic-pressure p for the existing synthetic single-region family. Patch fields, other field types, regions, and time-selection behavior remain outside this evidence. Complete counts remain 0/192 native, 0/717 integration, and 0/21 validated cleanroom workflows.
