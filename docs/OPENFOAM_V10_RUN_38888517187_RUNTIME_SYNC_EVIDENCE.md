# OpenFOAM Foundation v10 runtime synchronization evidence

## Run identity

- Repository: `3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform`
- Branch: `codex/openfoam-v10-boundary-input-audit-20261015`
- Code commit: `96e3868f3a38ffc6a98197bc3c46e6c70acadc1f`
- Pull request: [#1311](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/pull/1311)
- OpenFOAM workflow: [run 104](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38888517187), completed successfully on 2026-10-16
- OpenFOAM build: Foundation v10, `10-c4cf895ad8fa`
- Evidence artifact: [artifact 12040677819](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38888517187/artifacts/12040677819), 32,492,464 bytes
- Artifact SHA-256: `f89bc6e6f2837d4aa74ccccc8f9ee01d6011d7fe6b9a61c9ff894bb5ace0a617`

The artifact digest was independently reproduced after download. The ZIP CRC check passed. The workflow installed the pinned Foundation v10 distribution, generated and ran the synthetic cases with `blockMesh`, `checkMesh`, and `simpleFoam`, exported fields with `foamToVTK`, and ran the incremental synchronization step.

## Generated cases and mesh checks

The run contains three synthetic airflow configurations, each at coarse, medium, and fine resolution. Cell counts per mesh were 216, 1,728, and 13,824. All nine `checkMesh` logs reported `Mesh OK`. The independent volume audit passed for all nine cases; each mesh and its checkMesh report represented a 12.0 m³ room volume within the recorded serialization-based bounds.

The generated-input manifest contains 72 SHA-256 records. Independent replay matched every recorded input hash. The time-selection audit also passed for the selected solver times 50 and 100.

## Runtime synchronization and field integrity

The live synchronization workflow recorded nine completed cases and three output times per case (50, 100, and 150), for 27 synchronized records. Each record has a zero solver return code, a successful CleanroomX VTK import, and identified solver/configuration provenance.

For every synchronized record, CleanroomX imported velocity `U` in m/s and kinematic pressure `p` in m²/s². Surface flux `phi` was retained with units m³/s. Native-to-VTK comparisons passed for all 27 U fields and 27 p fields. Surface-`phi` parity passed for all 27 records using native mesh face geometry and orientation. Field dimensions, component counts, mesh-cell counts, and representation-specific tolerances are bound in the receipts.

The evidence includes 162 hash-checked synchronized assets: five VTK datasets and one `foamToVTK` log for each of the 27 time records. The separate incremental VTK synchronization report contains 27 accepted snapshots across the nine cases; independent replay matched each source VTK hash and CleanroomX snapshot hash. Its explicit field map imported pressure as kinematic pressure. Four turbulence fields were reported unavailable because the laminar cases did not produce them. No contaminant field was configured or produced, and the receipts report it as absent rather than substituting another field.

## Visualization follow-up on the current PR head

Commit `8927704de1d04ac105d43d71852bd516b597a514` adds a workflow step that reads the final-time VTK datasets directly from the runtime-sync store for configurations 1–3. [Foundation v10 run 106](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38889697945) completed successfully with the plot and report included in [artifact 12041675906](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38889697945/artifacts/12041675906). The artifact is 32,587,064 bytes with SHA-256 `8148c9ad6e1c8fdee150825648e45e76254c6ae7fcaf10aa57a98d38691284aa`; independent replay matched the digest and ZIP CRC.

The uploaded PNG is 102,669 bytes. Its JSON report records 72 sampled cell centers for each of the three configurations in a 0.5 m slab at y = 1.0 m, with speed values spanning 0.003429–0.222541 m/s. The report status is `sampled_cells_visualized_not_cfd_validation`; these samples are neither interpolated contours nor validation evidence.

## Numerical diagnostics and limits

All nine meshes passed the documented integrity checks, but this does not establish grid convergence. The logged final U and p residual screens are `NOT_BELOW_TOLERANCE` for all nine cases. Measured final inlet/outlet flux imbalance ranges from 0.005341% to 0.187145%; CleanroomX defines no project acceptance threshold for that quantity.

These are synthetic geometry and boundary-condition cases. The run verifies solver execution, output serialization, field mapping, synchronization, mesh-volume consistency, and hash-bound provenance receipts. It does not validate physical cleanroom performance, turbulence modeling, contaminant transport, ventilation effectiveness, ISO 14644 classification, or agreement with measured data. Scientific validation remains **BLOCKED** pending representative measured cleanroom data and a qualified benchmark. No grid-convergence index is claimed.

The solver logs also record `ExecutionTime` for 150 simpleFoam iterations per case. This run measured 0.0766–0.0774 CPU seconds for 216-cell cases, 0.3119–0.3332 seconds for 1,728-cell cases, and 2.0200–2.2243 seconds for 13,824-cell cases. These are run-specific CI measurements, not a controlled before/after performance benchmark; no optimization comparison is claimed.

## Automated tests

- Local full test suite at code commit `96e3868`: **2,497 passed, 81 skipped** in 133.92 seconds.
- Focused synchronization and time-selection tests at `96e3868`: **60 passed** in 0.81 seconds.
- [Required CI Gate run 4857](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38889697903) on commit `8927704`: passed. Python 3.11, 3.12, and 3.13 each report 2,497 passed and 81 skipped; Windows launcher, native BIM, wheel, and required-gate jobs passed.
- [CFD VTK Regression run 529](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38889697882) on commit `8927704`: passed.
- [Foundation v10 run 106](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38889697945) on commit `8927704`: passed, including runtime synchronization and visualization.
- [Foundation v10 run 104](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38888517187) on code commit `96e3868`: passed with the detailed field and mesh evidence above.

The local environment did not have OpenFOAM executables on PATH; actual solver evidence comes from the pinned Foundation v10 workflow, not from mocks or local tests.

## Reproduction entry points

See [the OpenFOAM pipeline guide](CFD_OPENFOAM_PIPELINE.md) for installation, case generation, execution, and synchronization commands. The exact workflow and case family are in [`.github/workflows/cfd-openfoam-grid.yml`](../.github/workflows/cfd-openfoam-grid.yml). The downloaded artifact is bound to workflow run 38888517187 and the code commit listed above.
