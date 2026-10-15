# OpenFOAM Foundation v10 run 63: native U/p to VTK boundary-patch parity

## Run and scope

- GitHub Actions run [38772855917](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38772855917) completed successfully on implementation commit `5453e3113bc4a8ab9eb7e18c5aaf003ba09742a3`.
- Runtime: OpenFOAM Foundation v10 build `10-c4cf895ad8fa`.
- Nine synthetic cases reached `150 s`; all 36 `blockMesh`, `checkMesh`, `simpleFoam`, and `foamToVTK` stages returned zero. Each `checkMesh` log reported `Mesh OK.`.
- The workflow now reopens the separate `inlet`, `outlet`, and `walls` VTK surface datasets. OpenFOAM Foundation v10 documents `patchWriter` as writing volume fields to patch output ([source](https://cpp.openfoam.org/v10/patchWriter_8H_source.html)).
- Evidence artifact [11992892011](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38772855917/artifacts/11992892011), archive SHA-256 `d40b603f871758be1dc4b05f6c78eeb4302e96f4ec6fd0af841b618c688e54c9`.

## Boundary-patch parity method

The audit reads each patch's legacy VTK `POLYDATA`, `patchID`, cell-data `U`, and cell-data `p`. It verifies the exported patch index and face count against the native `constant/polyMesh/boundary` dictionary, then maps each VTK face to the native face by a complete, unique vertex-coordinate signature at the workflow's six-significant-digit ASCII precision. It does not infer face identity from VTK cell order.

For each mapped face, the audit compares VTK U and p with the native final-time boundary field. It reads explicit uniform or nonuniform values, resolves `zeroGradient` values from the owning native cell, and applies the `noSlip` zero-velocity condition. Those are the boundary types present in this synthetic family:

| Patch | U boundary type | p boundary type | Datasets | Faces | U components | p values |
|---|---|---|---:|---:|---:|---:|
| inlet | `fixedValue` | `zeroGradient` | 9 | 462 | 1,386 | 462 |
| outlet | `pressureInletOutletVelocity` | `fixedValue` | 9 | 1,197 | 3,591 | 1,197 |
| walls | `noSlip` | `zeroGradient` | 9 | 11,949 | 35,847 | 11,949 |
| **Total** |  |  | **27** | **13,608** | **40,824** | **13,608** |

All compared values passed the case-specific float32/ASCII serialization bounds. Worst absolute errors and largest corresponding bounds across each patch class were:

| Patch | U max absolute error (m/s) | U max bound (m/s) | p max absolute error (m²/s²) | p max bound (m²/s²) |
|---|---:|---:|---:|---:|
| inlet | 5.96046448e-9 | 5.14901161e-7 | 5.00518100e-9 | 5.46566129e-9 |
| outlet | 5.05344792e-7 | 5.14901161e-7 | 0 | 1.40129846e-45 |
| walls | 0 | 1.40129846e-45 | 4.97719158e-8 | 5.18626451e-8 |

The same artifact recheck reproduced run 61's internal-cell parity: 47,304 cells, 141,912 U components, and 47,304 p values mapped by `cellID`. The worst internal U and p absolute errors were `5.12711003e-7 m/s` and `5.06462888e-8 m²/s²`, respectively, within their recorded serialization bounds.

## Independent artifact recheck

After downloading the artifact, I verified its archive SHA-256, rehashed all 72 manifest-bound generated inputs and all 36 command logs, reimported and re-audited each internal U/p VTK dataset, then rehashed and recomputed all 27 boundary-patch audits from the archived native fields, mesh files, and VTK files. The patch summary total reproduced exactly: 13,608 faces, 40,824 U components, and 13,608 p values.

## Diagnostic limits and capability scope

This remains synthetic execution and file-parity evidence. All 18 terminal U/p residual screens are above their configured tolerances. The measured final-time flux imbalance ranges from `0.005341%` to `0.187145%`, and the project has no flux-balance acceptance criterion. Every case remains `DIAGNOSTIC_ONLY`; scientific validation and GCI eligibility remain blocked. This run does not establish physical correctness, mesh independence, or measured cleanroom correlation. Issue #1296 remains open.

`OF10-UTILITY-foamToVTK` and `OF10-VTK-IMPORT` remain `partial`. Other solver field types, patch geometries and boundary-condition families, regions, and time-selection behavior remain unverified. Complete counts remain 0/192 native, 0/717 integration, and 0/21 validated cleanroom workflows.
