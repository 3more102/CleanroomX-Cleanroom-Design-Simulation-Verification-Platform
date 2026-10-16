# OpenFOAM Foundation v10 run 90: explicit-time VTK evidence

## Provenance

- Workflow: [Foundation v10 run 90](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38867911839), on code commit `c4d4498b5691a3999996d9296765534cc6296b79`.
- Solver: OpenFOAM Foundation v10, build `10-c4cf895ad8fa`.
- Evidence archive [12032302330](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38867911839/artifacts/12032302330), 14,874,702 bytes, SHA-256 `6c703c5c1843a4eea865b51115fba2eb857efae1b43d58ba59a97908e1bb4783`.
- Nine synthetic cases completed all 36 baseline `blockMesh`, `checkMesh`, `simpleFoam`, and final-time `foamToVTK` stages successfully. The separate selected-time audit also passed for all nine cases.

## Explicit-time selection and parity

Each case ran `foamToVTK -time 100 -useTimeName` with `U`, `p`, and surface `phi`. All nine logs contain exactly `Time: 100` and one terminal `End` record. The independent archive replay matched the 72 generated-input hashes, all 36 baseline stage-log hashes and return codes, and the manifest and baseline execution-receipt hashes. It then verified 81 selected-time file records: nine command logs, 27 native `100/U`, `100/p`, and `100/phi` fields, and 45 VTK datasets.

The selected-time parity report records:

- Nine internal datasets: 47,304 cells, 141,912 velocity components, and 47,304 kinematic-pressure values.
- Twenty-seven `inlet`, `outlet`, and `walls` patch datasets: 13,608 faces, 40,824 velocity components, and 13,608 pressure values.
- Nine surface-`phi` datasets: 148,716 faces and 446,148 face-normal vector components.

Every native/VTK comparison passed within the recorded float32 and ASCII serialization bounds. The corrected aggregate `patch_faces_compared` is 13,608; per-case patch counts equal the complete native and VTK face coverage for all three patches.

The report contains 54 passing parity records: 18 internal U/p records, 27 patch records, and nine surface-phi records.

## Diagnostic limits

The receipt marks every case `DIAGNOSTIC_ONLY` and keeps `scientific_validation` `BLOCKED`. All 18 terminal `U`/`p` residual screens remain `NOT_BELOW_TOLERANCE`. Final-time flux imbalance ranges from 0.005341% to 0.187145%; no project flow-balance acceptance criterion is set. This run verifies only the exact time `100` for the existing synthetic single-region case family and its current fields and boundary patches. It does not establish multiple-time selection support, solver convergence, grid independence, physical correctness, or correlation with measured cleanroom data. The `OF10-UTILITY-foamToVTK` and `OF10-VTK-IMPORT` rows remain partial; completion counts remain 0/192 native, 0/717 integration, and 0/21 validated cleanroom workflows. Issue #1296 remains open.
