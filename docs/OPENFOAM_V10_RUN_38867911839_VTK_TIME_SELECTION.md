# OpenFOAM Foundation v10 run 90: explicit-time VTK selection

## Provenance

- Workflow: [Foundation v10 grid execution run 90](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38867911839), exact code head c4d4498b5691a3999996d9296765534cc6296b79.
- Solver: OpenFOAM Foundation v10, build 10-c4cf895ad8fa.
- Artifact: [12032302330](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38867911839/artifacts/12032302330), SHA-256 6c703c5c1843a4eea865b51115fba2eb857efae1b43d58ba59a97908e1bb4783. Independent download reproduced the artifact digest.

## Exact-time export checks

The run executed the nine generated synthetic cases at the recorded coarse, medium, and fine mesh levels. Each baseline blockMesh, checkMesh, simpleFoam, and foamToVTK stage completed successfully. The explicit-time audit then invoked foamToVTK with -time 100 -useTimeName once per case and required the log to contain exactly the selected Time: 100 record and a clean terminal End.

Independent artifact verification matched all 72 generated-input hashes and 36 baseline command-log hashes. The explicit-time receipt covers nine selected-time logs, 27 native U/p/phi field files, and 45 selected-time VTK outputs; every recorded file hash matched its archive bytes. The report records 54 passing parity results across internal U/p fields, inlet/outlet/walls patches, and surface phi. The corrected patch total is **13,608 faces**, summed only from matching native and VTK face counts.

| Evidence | Result |
| --- | ---: |
| Cases at selected time 100 | 9 |
| Baseline command stages | 36, all exit code 0 |
| Manifest input files | 72, all hashes match |
| Baseline stage logs | 36, all hashes match |
| Native U/p/phi field files | 27, all hashes match |
| Selected-time VTK outputs | 45, all hashes match |
| Internal, patch, and surface-phi parity records | 54, all PASS |
| Patch faces compared | 13,608 |

## Diagnostic limits

The configured terminal residual screen remains NOT_BELOW_TOLERANCE. Final-time flux imbalance spans 0.005341%–0.187145%; the project has no defined flow-balance acceptance criterion. These exports use generated synthetic inputs and demonstrate exact-time selection and serialization parity only. They do not establish solver convergence, grid independence, suitability of physical geometry, contaminant transport validity, or correlation with measured cleanroom data. Scientific validation stays BLOCKED; GCI eligibility and capability completion totals do not change.
