# OpenFOAM Foundation v10 run 66: residual-history diagnostic

## Provenance and scope

- GitHub Actions run [38776224839](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38776224839), on code commit `1870dae2a8051b14543fada6bd6b00026d1f47db`.
- OpenFOAM Foundation v10 build: `10-c4cf895ad8fa`.
- Workflow artifact [11993812155](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38776224839/artifacts/11993812155), SHA-256 `4e56f06cb0bfc188d3d7601edc8a82d023d27bc7d980110f6578cb11ac85d850`.
- Rechecked all nine `simpleFoam.log` SHA-256 values against `source_sha256` in the archived triage JSON. Each case contains 150 logged iterations and the parser reports no missing steps or fields.

This report describes the archived synthetic rectangular cases. It does not alter the case dictionaries or assign a project acceptance limit.

## Configured residual screen

The archived `system/fvSolution` dictionaries set `SIMPLE.residualControl` to `U 1e-6` and `p 1e-5`. At each logged iteration, a separate screen compared the largest of the `Ux`, `Uy`, and `Uz` initial residuals with the configured `U` value, and the `p` initial residual with its configured value. All 150 comparisons per field and per case were above those generated settings (1,350 comparisons per field).

The following terminal multiples are from the last logged iteration at `150s`. They quantify the parser's log-only comparison; they are not OpenFOAM's internal vector residual calculation or proof of nonlinear convergence.

| Case | U initial residual / configured U value | p initial residual / configured p value |
|---|---:|---:|
| configuration_1/coarse | 10,027× | 4,259× |
| configuration_1/medium | 522× | 446× |
| configuration_1/fine | 6,607× | 6,022× |
| configuration_2/coarse | 23,246× | 6,727× |
| configuration_2/medium | 52,810× | 12,796× |
| configuration_2/fine | 39,726× | 13,985× |
| configuration_3/coarse | 84,128× | 14,823× |
| configuration_3/medium | 123,065× | 23,028× |
| configuration_3/fine | 174,725× | 25,912× |

## Descriptive early/late residual medians

Each entry compares the median logged initial residual over iterations 1–30 with the median over iterations 121–150. `U` is the per-iteration maximum of the three component residuals; `p` is the scalar pressure residual.

| Case | U median, first 30 → last 30 | p median, first 30 → last 30 |
|---|---:|---:|
| configuration_1/coarse | 0.01431 → 0.01098 | 0.07450 → 0.04252 |
| configuration_1/medium | 0.01787 → 0.0006886 | 0.16042 → 0.004987 |
| configuration_1/fine | 0.04562 → 0.007635 | 0.39499 → 0.08050 |
| configuration_2/coarse | 0.03308 → 0.02253 | 0.11155 → 0.06469 |
| configuration_2/medium | 0.05919 → 0.04950 | 0.14485 → 0.12843 |
| configuration_2/fine | 0.08150 → 0.03822 | 0.20457 → 0.13405 |
| configuration_3/coarse | 0.12206 → 0.07272 | 0.22926 → 0.12626 |
| configuration_3/medium | 0.17089 → 0.12450 | 0.26174 → 0.23127 |
| configuration_3/fine | 0.17243 → 0.15445 | 0.24637 → 0.24998 |

These window medians are descriptive only. U is lower in the later window in all nine cases; p is lower in eight and slightly higher for configuration 3/fine. Every case remains above the generated residual screen throughout the logged iterations, so the medians do not establish convergence or stability of engineering quantities of interest. They do not identify the cause of the residual behavior.

## Status and limits

All cases remain `DIAGNOSTIC_ONLY`; scientific validation remains `BLOCKED`. The archived input is synthetic, the project has not defined solver-residual or flow-balance acceptance criteria, and no measured cleanroom data or uncertainty analysis is included. Do not change the synthetic model or solver settings on the basis of this diagnostic alone. Issue #1296 remains open, and these data do not make the grid families eligible for GCI acceptance.
