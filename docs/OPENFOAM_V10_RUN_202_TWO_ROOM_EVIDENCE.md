# OpenFOAM Foundation v10 run 202: two-room execution evidence

- Workflow: [OpenFOAM Foundation v10 run 202](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/39040785464)
- Repository head: `d0765769638d5dc674b59be657263e8966484095`
- Solver: OpenFOAM Foundation v10
- Evidence artifact: [artifact 12103059743](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/39040785464/artifacts/12103059743)
- Artifact ZIP SHA-256: `1346fc829e6881d86ee8db3e663592cd694f5ee8a435cb82b2127342936a4a10`
- Two-room receipt SHA-256: `08aa3fc68bf436a192936089aabb9d21c38da6fb20fac475ee30616aa5c0861a`
- Case manifest SHA-256: `7c7be3f54856b7713e3fe43f6f9b69d54aed91de2e95637018ee1267ecd5d44f`

## Recorded execution

All four Foundation v10 commands returned code 0: `blockMesh`, `checkMesh`,
`simpleFoam`, and `foamToVTK`. `checkMesh` reported `Mesh OK` for 2,304
hexahedral cells. The final probe time was 150 with 151 samples.

Using the declared density of 1.2 kg/m³ to convert OpenFOAM kinematic pressure,
the recorded room 1 minus room 2 pressure difference was 5.7843749615 Pa. It
fell inside the synthetic fixture's declared 5 ± 1 Pa band. This only verifies
that this pinned case met its own software smoke threshold.

The final-time solver flux report measured 0.1000000000 m³/s net inward at the
inlet and 0.0988250913 m³/s net outward at the outlet, with 1.1749086772%
relative imbalance. The report correctly labels flow balance
`NO_PROJECT_ACCEPTANCE_CRITERION`; no acceptance limit was configured.
Solver convergence was `NOT_ASSESSED`, and scientific validation remains
`BLOCKED`.

## Evidence boundary

The uploaded archive's SHA-256 matched the digest returned by GitHub. Replaying
the run receipt through the original PR #1326 ProofGraph adapter verified the
case-input, stage-log, probe, final-time `phi`, and mesh-boundary hashes. That
receipt used schema v1 and did not include hashes for the files under `VTK/`,
even though `foamToVTK` produced visualization output. It is therefore
historical solver-integration evidence, not a complete VTK asset-integrity
receipt.

The follow-up receipt schema v2 records every VTK asset hash and makes
ProofGraph reject changed, added, removed, linked, or oversized VTK outputs.
Run 202 cannot be exported under that stronger check; rerun the case with the
v2 runner to produce a fully VTK-bound receipt. Hash consistency does not
authenticate the run, establish convergence, or validate physical cleanroom
performance.
