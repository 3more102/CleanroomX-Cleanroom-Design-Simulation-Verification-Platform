# OpenFOAM Foundation v10 run 70: VTK flux and checkMesh evidence

## Provenance

- Workflow: [Foundation v10 grid run 70](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38780408294), on code commit `6cffb8fef090a4916074df0c9c10fe8ca3b97e2c`.
- Solver: OpenFOAM Foundation v10, build `10-c4cf895ad8fa`.
- Evidence archive [11996486504](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38780408294/artifacts/11996486504), 11,894,433 bytes, SHA-256 `8702b5cf85e961b5813003f8f9a4dc6ebe418a8c4295e820b601bcd4c0857f74`.
- Nine explicitly synthetic cases completed 36/36 `blockMesh`, `checkMesh`, `simpleFoam`, and `foamToVTK` command stages with return code 0. All cases reached final time 150 s.

An independent archive recheck reproduced all 72 generated input hashes and all 36 raw command-log hashes. It also matched the receipt hashes for the native fields, polyMesh files, internal VTK datasets, surface-field VTK datasets, and 27 patch datasets.

## Field export parity

The receipt reports native-to-VTK parity within the recorded float32 and ASCII serialization bounds:

- Nine internal datasets: 47,304 cells, 141,912 velocity components, and 47,304 kinematic-pressure values.
- Twenty-seven inlet/outlet/walls patch datasets: 13,608 faces, 40,824 velocity components, and 13,608 pressure values.
- Nine surface `phi` datasets: 148,716 faces and 446,148 vector components. The audit checks the native oriented face flux against the VTK vector and verifies face ordering through serialized face centres.

Each `checkMesh` log has a complete hash-bound diagnostic summary. All nine report the solver marker `Mesh OK.` with no reported failed checks. Project mesh acceptance remains `not_assessed_no_project_criteria`; the tool output does not define project quality limits.

## Diagnostic limits

The run receipt remains `executed_requires_convergence_review`. All 18 terminal U/p residual screens remain above their generated tolerances. Measured final-time flux imbalance ranges from 0.005341% to 0.187145%; no project flow-balance acceptance criterion is set. The triage JSON remains `DIAGNOSTIC_ONLY` and scientific validation `BLOCKED`.

These results establish synthetic execution and serialization evidence only. They do not establish physical correctness, mesh independence, or measured cleanroom correlation. Issue #1296 and the relevant capability-matrix rows remain open or partial.
