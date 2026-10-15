# OpenFOAM Foundation v10 grid run triage

## Scope and provenance

This report summarizes the nine-case workflow run [38666633298](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38666633298)
on commit `4a3e595a97f5e988dc0165fb6ce0b35cc7954293`. The run used the
synthetic family in `examples/cfd_grid_family.example.json`, with a 150-step
solver end time, and OpenFOAM Foundation v10 build `10-c4cf895ad8fa`.

The workflow verified all 72 generated solver-input digests against the
generation manifest before execution. All nine cases completed `blockMesh`,
`checkMesh`, and `simpleFoam`: 27/27 commands returned zero, and every
`checkMesh` log contained `Mesh OK.`. Each solver log has 150 parsed time
steps and a terminal `End` marker. These results establish successful
execution and log structure for this synthetic run; they do not establish
convergence or physical validity.

The evidence artifact is [openfoam-v10-grid-evidence-91eefb7cdcd1b6440167a8b20ef9abd0a428fc17](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38666633298/artifacts/11942270643),
artifact ID `11942270643`, SHA-256
`8615f8c6fd0175ee3867805c016656fb2f7e25d68671fa46981d558debfb166f`. GitHub
scheduled its expiration for 2026-10-29.

## Solver-input consistency

The JSON triage report has top-level input-screen status
`BYTE_IDENTICAL_ACROSS_GRID_LEVELS`. In each of the three configurations,
the hashes of these seven dictionaries match across coarse, medium, and fine:

- `0/U`
- `0/p`
- `constant/physicalProperties`
- `constant/momentumTransport`
- `system/controlDict`
- `system/fvSchemes`
- `system/fvSolution`

`system/blockMeshDict` was hashed separately; its digest differs across the
three grid levels in each configuration. This confirms byte consistency for
the declared solver-condition files in this generated run. It does not prove
that the boundary conditions are correct, that inlet patch areas and flow
rates agree with the intended design, or that the geometries are physically
equivalent.

## Terminal logged residual screen

The table gives each case's terminal logged initial linear-residual ratio to
the tolerance printed in its log. For `U`, the diagnostic uses the largest
logged `Ux`, `Uy`, or `Uz` initial residual divided by the `U` tolerance. For
`p`, it uses the logged `p` initial residual divided by its tolerance. Ratios
above 1 mean the logged initial residual was not below that criterion. The
vector `U` value is a conservative log proxy and does not reproduce
OpenFOAM's internal vector `residualControl` calculation.

| Configuration | Grid | U ratio | p ratio |
|---|---|---:|---:|
| 1 | coarse | 10,027.27 | 4,258.74 |
| 1 | medium | 521.95 | 446.26 |
| 1 | fine | 6,607.46 | 6,022.20 |
| 2 | coarse | 23,246.11 | 6,727.46 |
| 2 | medium | 52,809.97 | 12,795.96 |
| 2 | fine | 39,726.11 | 13,984.50 |
| 3 | coarse | 84,128.39 | 14,823.12 |
| 3 | medium | 123,064.92 | 23,027.68 |
| 3 | fine | 174,725.41 | 25,911.71 |

All 18 terminal comparisons exceed their configured tolerances. The family
log status is `DIAGNOSTIC_ONLY`, the configured residual screen is
`NOT_BELOW_TOLERANCE`, and `scientific_validation` remains `BLOCKED`. A clean
process exit and terminal `End` are not convergence criteria.

## Next engineering work

Review the generated boundary conditions against inlet patch areas and target
flows. Do not relax residual tolerances to make the screen pass. Investigate
solver and model settings, then rerun the cases and compare converged quantities
of interest on all three grids. No VTK fields or mesh-convergence result were
produced in this run, so it does not support a GCI estimate or a
CleanroomX/OpenFOAM compatibility percentage. Physical validation still
requires comparison with measured cleanroom data and uncertainty.
