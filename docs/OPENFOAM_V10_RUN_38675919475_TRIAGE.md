# OpenFOAM Foundation v10 run 38675919475: flux and convergence review

## Provenance and execution

The nine-case workflow ran on commit `42545cdfcd1d3ec829738a52f4fa5c1930b20db7`
using OpenFOAM Foundation v10 build `10-c4cf895ad8fa` and the explicitly
synthetic family in `examples/cfd_grid_family.example.json`. All 72 generated
input digests and all nine boundary-input audits passed before execution.

All nine cases reached the logged final time `150s` and completed
`blockMesh`, `checkMesh`, and `simpleFoam`: 27/27 commands returned zero, and
each `checkMesh` log contained `Mesh OK.`. Every solver log was structurally
triaged with 150 time steps. The run status is
`executed_requires_convergence_review`; successful process exits and mesh
markers do not mean the cases converged.

The evidence artifact is [openfoam-v10-grid-evidence-4ff1b668efaba89c5b829806f42e8f4e6a48c86e](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38675919475/artifacts/11945878362),
artifact ID `11945878362`, SHA-256
`e26785d3bc931c10ce2cab40378fd4950778b84aa9b296fd9a7b46c173f9fb01`.
GitHub scheduled its expiration for 2026-10-29.

## Generated input boundary audit

For all nine cases the audit reconstructed `blockMeshDict` face areas and
outward normals, checked the generated `U` and `p` patch types, and integrated
the prescribed inlet normal velocity. The input flow is `0.15 m³/s` for each
case; the recomputed values agree within floating-point round-off. The audit
keeps actual solver outlet flux and flow balance as `not_measured`; those are
reported separately below from the final-time `phi` files.

## Final-time solver flux

The triage tool reads signed `phi` values at the last logged time, checks the
patch values against `nFaces` in `constant/polyMesh/boundary`, and reports net
inlet/outlet flows, reverse flow, wall flux, and net boundary flux. For this
incompressible run, `phi` is the face flux created from `fvc::flux(U)` in the
pinned Foundation v10 [`createPhi.H`](https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/src/finiteVolume/cfdTools/incompressible/createPhi.H).

| Case | Net inlet inflow (m³/s) | Net outlet outflow (m³/s) | Reverse outlet inflow (m³/s) | Relative boundary-flux imbalance |
|---|---:|---:|---:|---:|
| 1 / coarse | 0.150000000 | 0.149863793 | 0.005590868 | 0.090804% |
| 1 / medium | 0.150000000 | 0.150008012 | 0.022107697 | 0.005341% |
| 1 / fine | 0.150000000 | 0.150186394 | 0.006768355 | 0.124263% |
| 2 / coarse | 0.150000000 | 0.149719282 | 0.000000000 | 0.187145% |
| 2 / medium | 0.150000000 | 0.149862684 | 0.000000000 | 0.091544% |
| 2 / fine | 0.150000000 | 0.149946582 | 0.000000000 | 0.035612% |
| 3 / coarse | 0.150000000 | 0.149743598 | 0.000000000 | 0.170935% |
| 3 / medium | 0.150000000 | 0.149893535 | 0.000000000 | 0.070977% |
| 3 / fine | 0.150000000 | 0.149915670 | 0.000000000 | 0.056220% |

The reported relative imbalance is `100 × |net boundary outward flux| / gross
inlet inflow`. The measured values range from `0.005341%` to `0.187145%`.
The project has not defined a flow-balance acceptance criterion, so the result
is `MEASURED_DIAGNOSTIC_ONLY` and records
`NO_PROJECT_ACCEPTANCE_CRITERION`. Configuration 1 also shows reverse flow at
the pressure outlet; this is reported explicitly and is not assigned an
acceptance threshold.

## Residual and engineering status

All 18 terminal logged `U`/`p` residual comparisons remain above their
configured tolerances. The `U` ratio to tolerance ranges from approximately
`522` to `174,725`; the `p` ratio ranges from approximately `446` to `25,912`.
The log status is `DIAGNOSTIC_ONLY`, the configured residual screen is
`NOT_BELOW_TOLERANCE`, and `scientific_validation` remains `BLOCKED`.

The run used synthetic geometry and flow inputs. It did not produce VTK output
for three-grid QoI/GCI analysis, justify the laminar model for a physical
cleanroom, or compare predictions against independent cleanroom measurements.
The measured flux imbalance is a solver-output diagnostic, not a substitute
for residual convergence, mesh independence, or physical validation. No
CleanroomX/OpenFOAM compatibility percentage is derived from this run.
