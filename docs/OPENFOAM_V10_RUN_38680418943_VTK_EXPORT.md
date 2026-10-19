# OpenFOAM Foundation v10 run 56: VTK export evidence

## Run identity

- Workflow run: [OpenFOAM Foundation v10 run 56](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38680418943)
- Commit: `8c6f41bbcb1636f4117eea256f04426cf5341c7e`
- Solver build: `10-c4cf895ad8fa`
- Cases: nine explicitly synthetic cases (three configurations x coarse/medium/fine)
- OpenFOAM command stages: 36/36 succeeded: `blockMesh`, `checkMesh`, `simpleFoam`, and `foamToVTK` for each case
- Execution artifact: [11948056355](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38680418943/artifacts/11948056355)
- GitHub artifact archive SHA-256: `6ecfea97466c9cb618273e5dcad6ef0a6675e4c1597590e4a603b388f73ca5e4`
- On this implementation head, CI [4804](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38680418800) and CFD VTK Regression [429](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38680419020) passed.

The workflow exported final-time cell velocity `U` with `foamToVTK`, imported each VTK using CleanroomX, and checked the three-component velocity, finite positive cell volumes, manifest-bound cell count, and source SHA-256. The post-run summary re-opened all nine datasets and repeated these checks.

I downloaded the uploaded archive and independently checked its advertised archive digest. All nine VTK byte digests matched the execution receipt, and all nine cell counts matched the generated-input manifest.

## VTK datasets

Each entry is the SHA-256 of the actual legacy `.vtk` internal dataset in the run artifact.

| Configuration | Coarse (216 cells) | Medium (1,728 cells) | Fine (13,824 cells) |
|---|---|---|---|
| 1 | `c30f14a36d177b4b58dd79714902a42905f14b5d813360a38ad398907806ef0d` | `340aa0f3f291a260bcb706340aa76b32595160caf3a0a99c2899d901bca9352d` | `0c269a6f806ba56234a533a7fd05f54ba132d7aa5d50c60a332697f2d9f700f3` |
| 2 | `fa22aebd3a7e7ff4fe3fd4ca99e3995151bbd8abe7929f6ddca633df0e65f297` | `f7e96e80254e2c5d83d78bb0e43a7cdcfda753550562f885f4d72624d7f55f05` | `f5304b551370171ce906816c7c7ca4c66be830a19427c8f135c538294fc5263c` |
| 3 | `db3b8b1e7d4e094e013a920e756a58e969daf40f69fa1a7baee6e84b69622d99` | `4213fad15ff7deee69e201667635f0064ae3521015ecdd5d82d152210d44d0d8` | `d9105f06de103b698bfc8588eff1aba625fe9a71f168704be9236b3f3a83759b` |

## Diagnostic limits

The triage JSON in the artifact reports `DIAGNOSTIC_ONLY` and
`scientific_validation=BLOCKED`.

- The log-based terminal residual screen is above its displayed tolerance for all nine `U` comparisons and all nine `p` comparisons.
- Final-time signed `phi` flux imbalance ranges from 0.005341% (configuration 1 medium) to 0.187145% (configuration 2 coarse). No project flow-balance acceptance criterion is defined.
- The pressure outlet has reverse inward flux in all three configuration 1 grid levels.
- Declared non-mesh condition dictionaries are byte-identical across coarse, medium, and fine meshes within each configuration; this does not prove correct physical inputs or convergence.

The VTK export proves execution and data ingestion only. It does not show residual convergence, nonlinear convergence, accepted flow balance, mesh independence, GCI eligibility, measured cleanroom correlation, or scientific validation. The current VTK capability rows remain `partial`; the parity scores remain 0/192 native, 0/717 integration, and 0/21 validated cleanroom workflows.
