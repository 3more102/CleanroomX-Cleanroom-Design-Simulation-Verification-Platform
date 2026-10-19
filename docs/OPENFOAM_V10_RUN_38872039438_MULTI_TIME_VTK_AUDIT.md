# OpenFOAM Foundation v10 run 94: multi-time VTK audit

## Provenance

- Workflow: [Foundation v10 run 94](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38872039438), on code commit `f94a80a3b242063b13c95236c37d6c112a6f1bf1`.
- Solver: OpenFOAM Foundation v10, build `10-c4cf895ad8fa`.
- Evidence archive [12033234866](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38872039438/artifacts/12033234866), 17,817,800 bytes, SHA-256 `fa5b85af0e8ed2470101747540f22808032ba1959c0f41548551b62a24f060a3`.
- All nine synthetic cases completed the baseline `blockMesh`, `checkMesh`, `simpleFoam`, and `foamToVTK` stages with exit code 0. The separate multi-time export and parity audit also completed.

## Exact-time selection and field parity

Each case ran `foamToVTK -time 50,100 -useTimeName -fields '( U p phi )' -surfaceFields -ascii -poly -noPointValues`. Every utility log contains exactly the ordered `Time: 50` and `Time: 100` records and one terminal `End`.

The audit checked both native time directories for all nine cases, producing 18 case-time pairs. It compared internal-cell `U` and `p`, `inlet`/`outlet`/`walls` patch `U` and `p`, and surface `phi`. The 108 parity records passed within the recorded float32/ASCII serialization bounds:

- 18 internal datasets: 94,608 cells, 283,824 velocity components, and 94,608 pressure values.
- 54 patch datasets: 27,216 faces.
- 18 surface-`phi` datasets: 297,432 faces and 892,296 face-normal vector components.

The sidecar reports `selection_and_serialization_diagnostics_passed`, marks every case `DIAGNOSTIC_ONLY`, and retains `scientific_validation: BLOCKED`.

## Independent artifact replay

The downloaded archive SHA-256 matched GitHub's artifact digest. Independent replay verified:

- All 72 generated-input hashes from `manifest.json`.
- All 36 baseline stage-log hashes from the execution receipt.
- The manifest and baseline execution-receipt hashes recorded by the VTK audit.
- All 153 selected-time records: nine command logs, 54 native field files, and 90 VTK datasets. Each file's SHA-256 and byte count matched the sidecar.
- Zero failed baseline stages and exact selected-time logs for all nine cases.

## Limits

This verifies exact selection of times `50` and `100` for the current synthetic single-region case family and current field and boundary-condition types. It does not verify arbitrary ranges, zero-time inclusion, other fields or patch conditions, convergence, grid independence, model validity, or measured cleanroom correlation. Scientific validation remains blocked; issue #1296 stays open and the capability rows stay partial.
