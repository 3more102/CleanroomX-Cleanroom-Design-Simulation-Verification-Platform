# OpenFOAM Foundation v10 600-step run triage

## Scope and provenance

This is a read-only diagnostic of the nine-case artifact from GitHub Actions
run [38518690225](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38518690225).
The run used branch `codex/cfd-refinement-stable-patches-20261014` at source
commit `4ba3b627c1e129d7f653c943106629ea6783868e`. The downloaded artifact
was `openfoam-v10-grid-evidence-3088c0f49a021e5e3999b747e5a46abeccb7acd6`
(artifact ID `11873400874`; archive SHA-256
`e49a8e49461b944c43e93e3beedf244f8e9c32cfd3d40bb3e98c6eecded2ff61`).

All 27 recorded `blockMesh`, `checkMesh`, and `simpleFoam` stage logs had
matching recorded SHA-256 digests; all 72 case input files matched the source
manifest. The three commands returned zero in all nine cases. Each
`checkMesh` log reports `Mesh OK`; the recorded maxima are aspect ratio
about 1.5, non-orthogonality 0, and skewness about 2.13e-14.

The receipt identifies Foundation v10, nine cases, status
`executed_requires_convergence_review`, engineering review `BLOCKED`, and
physical validation `not_performed`. Each `simpleFoam` log has 600 time
steps and a terminal `End`. This is the 600-step artifact. It is distinct
from the separate 5,000-iteration diagnostic discussed in PR #1304.

## Terminal logged residual screen

For each case, the velocity ratio is the largest of the terminal logged
`Ux`, `Uy`, and `Uz` initial linear residuals divided by the logged
`U` tolerance (`1e-6`). The pressure ratio is the terminal logged `p`
initial linear residual divided by its logged `p` tolerance (`1e-5`).
Ratios above 1 mean the logged initial residual was not below that criterion.

| Configuration | Grid | U ratio | p ratio |
|---|---|---:|---:|
| 1 | coarse | 10,575.41 | 4,214.41 |
| 1 | medium | 591.22 | 539.64 |
| 1 | fine | 113.25 | 215.87 |
| 2 | coarse | 49,748.98 | 12,293.47 |
| 2 | medium | 1,383.28 | 554.63 |
| 2 | fine | 4,258.75 | 3,937.81 |
| 3 | coarse | 31,924.90 | 6,848.76 |
| 3 | medium | 16,313.42 | 8,815.37 |
| 3 | fine | 14,580.40 | 12,808.89 |

All 18 terminal logged comparisons are above their configured thresholds.
The nine logs are complete and parseable, but the family residual screen is
`NOT_BELOW_TOLERANCE`. The `U` calculation is a conservative component
proxy; it does not reproduce OpenFOAM's internal vector residual-control
calculation. These ratios are a linear-residual screen only and do not establish
nonlinear convergence or quantify solution error.

## Interpretation and next work

The current model inputs describe a synthetic, steady, isothermal, laminar
case. They do not include turbulence, buoyancy, particle transport, or an
underfloor plenum. The logs do not identify a root cause for the residual
behavior. Do not relax tolerances to make the screen pass. Review the
Foundation v10 dictionaries, boundary conditions, flux/continuity behavior,
and model applicability first; then decide whether a justified solver/model
change and a longer run are needed. A defensible mesh-independence study also
requires comparable, converged quantities of interest on all three grids,
followed by comparison with measured cleanroom data and uncertainty.

Issue #1296 remains open. This report does not close its evidence gaps and
does not claim physical validation or a CleanroomX/OpenFOAM compatibility
percentage.
