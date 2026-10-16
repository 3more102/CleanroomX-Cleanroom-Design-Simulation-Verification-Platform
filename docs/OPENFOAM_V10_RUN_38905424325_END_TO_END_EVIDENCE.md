# OpenFOAM Foundation v10 run 38905424325 evidence

## Status

**PARTIALLY COMPLETE — solver execution and data ingestion verified; scientific
validation blocked.** This report records a real OpenFOAM run, not a mocked
solver. A successful process and matching exported fields do not establish
engineering accuracy or cleanroom performance.

## Reproducibility record

| Item | Evidence |
| --- | --- |
| Repository | `3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform` |
| Pull request | [#1311](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/pull/1311) |
| Branch at execution | `codex/openfoam-v10-boundary-input-audit-20261015` |
| Commit at execution | `f57cde28bc2357d5b2f194f622308dc29ac7117d` |
| OpenFOAM workflow | [Run 38905424325](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38905424325) |
| Artifact | [ID `12047563804`](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38905424325/artifacts/12047563804); SHA-256 `9224905fe3ec1efd76a46438596b0fd0966cb6dc0290323e26424a4f8491f464` |
| Solver distribution | OpenFOAM Foundation v10, build `10-c4cf895ad8fa` |
| Companion CI | [Python/CI run 38905424147](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38905424147); [VTK regression run 38905424125](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38905424125) |

The workflow uploaded the artifact after all stages succeeded. A local replay
verified that its SHA-256 matches GitHub's artifact metadata, then checked the
simulation records, receipts, synchronized field assets, and plotted-result
metadata against the files in the archive.

## Executed workflow

- Nine synthetic airflow cases covered three room-layout configurations at
  216, 1,728, and 13,824 cells. The room volume audit reported 12.0 m³ for
  each generated mesh.
- All nine cases completed `blockMesh`, `checkMesh`, `simpleFoam`, and
  `foamToVTK`: 36 successful tool stages. OpenFOAM reported each mesh's
  geometric checks as OK. These are tool-reported mesh checks; no separate
  project-specific mesh-acceptance criteria were applied.
- The native runtime synchronizer recorded completed results at times 50,
  100, and 150 for each airflow case. The VTK import report contains 27
  snapshots across nine cases and is classified
  `PASS_DATA_INGESTION_DIAGNOSTIC_ONLY`.
- A separate real `scalarTransportFoam` case used the coarse 216-cell mesh and
  produced synchronized results at times 40, 80, 120, and 124. Its report
  requires `U` and `T`; all four records passed the native-to-VTK field parity
  checks. `U` is in m/s. `T` has dimensions `[0 0 0 0 0 0 0]` and is explicitly
  mapped as `normalized_tracer` with unit `1`. It is not temperature or
  measured contaminant concentration. The solver log reported convergence in
  124 SIMPLE iterations; the project's residual acceptance remains
  `not_assessed`.
- The workflow rendered a sampled airflow-speed cross-section for all three
  configurations, with 72 cells per configuration. The JSON sidecar declares
  speed units as `m/s` and classifies the output
  `sampled_cells_visualized_not_cfd_validation`.

No files were transferred manually between the solver and the workflow's
synchronization/import steps.

## Automated test evidence

At the same code head, the complete Python test suite passed on Python 3.11,
3.12, and 3.13: **2,518 passed and 81 skipped per version**. The separate
Python 3.13 GUI smoke step passed 48 tests. The Windows launcher smoke,
native BIM smoke, doctor-wheel smoke, and Required CI Gate all passed. The
focused local OpenFOAM/scalar/visualization tests passed **57 tests**. The
Foundation v10 and VTK regression workflow runs also completed successfully.
Skipped tests remain skipped as reported by CI; they are not counted as
passes.

## Numerical screening and limits

- All 18 terminal velocity/pressure residual-control screens across the nine
  airflow cases were **not below their configured tolerances**.
- The diagnostic flow-imbalance values range from **0.00534133556299% to
  0.187145329221%**. The project defines no acceptance criterion for these
  values, so they are not pass/fail evidence for mass conservation.
- The three mesh sizes provide executable mesh-family coverage, but no
  accepted grid-convergence index, uncertainty bound, or mesh-independent
  result is established.
- `checkMesh` success, solver exit status, solver log convergence text, and
  field parity each test a different software or numerical property. None
  independently validates the cleanroom physics.

### Evidence-gated three-grid audit

I also ran `cleanroomx-cfd-pipeline grid-audit` on each configuration using
the run 125 artifact's actual final-time cell-velocity VTK files and matching
`simpleFoam` logs. The VTK QoI is volume-weighted mean speed; the imported
cell volumes sum to 12.0 m³ for every level. The study inputs and unedited CLI
results are preserved under
[`docs/evidence/openfoam-run-38905424325/`](evidence/openfoam-run-38905424325/).
The input studies reference files inside the linked run artifact and record
the corresponding VTK and log SHA-256 values in each result.

| Configuration | Fine / medium / coarse mean speed (m/s) | Observed order | Fine-grid GCI | Audit result |
| --- | --- | --- | --- | --- |
| 1 | 0.07902352 / 0.07038684 / 0.06400471 | Not available | Not available | `indeterminate_or_failed` |
| 2 | 0.03134407 / 0.03549246 / 0.03833825 | Not available | Not available | `indeterminate_or_failed` |
| 3 | 0.02893993 / 0.03162543 / 0.03314556 | Not available | Not available | `indeterminate_or_failed` |

All three audits exited with code 3, which is the CLI's ineligible/indeterminate
result. Each reports failed solver residual screening on all three levels and
no positive three-grid power-law order for this QoI; therefore no Richardson
estimate or GCI was produced. The study JSON copies the distributed example
criteria to make the diagnostic run reproducible. Those sample limits are not
project-approved acceptance criteria and this run does not treat them as such.
The condition fingerprint in each study is computed from each layout and flow
descriptor plus SHA-256 digests of the shared non-mesh solver inputs
(`0/U`, `0/p`, physical properties, momentum transport, `controlDict`,
`fvSchemes`, and `fvSolution`). The archived per-grid mesh/input manifests
remain the provenance for geometry and boundary audits; a matching fingerprint
alone is not proof of physically equivalent conditions.

This run does not provide measured-room correlation, validated diffuser/fan/
filter or perforated-floor models, a validated turbulence or buoyancy model,
particle-transport physics, measured contaminant source data, temperature-field
validation, benchmark correlation, or energy-conservation acceptance. It does
not establish an ISO 14644 classification. A before/after performance benchmark
was not run. Only OpenFOAM Foundation v10 is runtime-qualified by this evidence;
other distributions and releases remain unverified.

## Acceptance assessment

Verified: automatic case generation and execution for the synthetic v10 cases,
stable-result synchronization, native/VTK field parity, passive-scalar field
mapping, and sampled visualization. Still required for engineering completion:
project-specific residual and flux criteria, accepted mesh-convergence and
uncertainty studies, physically representative cleanroom geometry and models,
measured or recognized benchmark correlation, and reproducible performance
measurements. Overall integration status is therefore **PARTIALLY COMPLETE**.
