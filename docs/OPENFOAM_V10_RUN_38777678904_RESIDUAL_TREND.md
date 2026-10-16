# OpenFOAM Foundation v10 run 67 residual-trend diagnostic

## Provenance and scope

- Workflow run: [38777678904](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38777678904), OpenFOAM Foundation v10 grid execution run 67.
- Downloaded evidence artifact: `11994032855`; independently verified archive SHA-256: `4e8725c04924f947a60623ba5c36993decba51fe6bf0cf21e4f5b923ffb8411f`.
- The nine cases are synthetic rectangular layout/grid fixtures. This is a log diagnostic of that artifact, not a physical cleanroom case or validation result.
- Reproduction: run `cleanroomx-cfd-grid-triage <family-root> --window 5 --trend-window 50` against the extracted `cleanroomx-cfd-grid-family` directory.

## Method

For each logged field (`Ux`, `Uy`, `Uz`, `p`) in each case, compare the median of the first 50 logged initial linear residuals with the median of the last 50. The windows are disjoint. All nine logs contain 150 samples per field. The reported ratio is `tail median / initial median`; it is descriptive and adds no pass/fail criterion.

## Results

| Case | Field | First-window median | Tail-window median | Tail / initial |
| --- | --- | ---: | ---: | ---: |
| configuration_1/coarse | Ux | 0.0085168165 | 0.008432739 | 0.99012806 |
| configuration_1/coarse | Uy | 0.011369023 | 0.010979088 | 0.96570198 |
| configuration_1/coarse | Uz | 0.0069436088 | 0.0069950959 | 1.00741503 |
| configuration_1/coarse | p | 0.04385722 | 0.04251746 | 0.96945178 |
| configuration_1/medium | Ux | 0.0028989495 | 0.00050431614 | 0.17396513 |
| configuration_1/medium | Uy | 0.0034143823 | 0.00066479152 | 0.19470331 |
| configuration_1/medium | Uz | 0.0019666577 | 0.00030324498 | 0.15419307 |
| configuration_1/medium | p | 0.035191362 | 0.0047572031 | 0.13518099 |
| configuration_1/fine | Ux | 0.015090818 | 0.0061760398 | 0.40925812 |
| configuration_1/fine | Uy | 0.016140322 | 0.0082321937 | 0.51003901 |
| configuration_1/fine | Uz | 0.0080886653 | 0.0043511986 | 0.53793777 |
| configuration_1/fine | p | 0.18548915 | 0.084308759 | 0.45452125 |
| configuration_2/coarse | Ux | 0.008326791 | 0.0083419957 | 1.00182600 |
| configuration_2/coarse | Uy | 0.02474739 | 0.02219859 | 0.89700732 |
| configuration_2/coarse | Uz | 0.015833727 | 0.015056426 | 0.95090855 |
| configuration_2/coarse | p | 0.071281052 | 0.064226123 | 0.90102660 |
| configuration_2/medium | Ux | 0.010364414 | 0.01031251 | 0.99499210 |
| configuration_2/medium | Uy | 0.0461052 | 0.050717785 | 1.10004480 |
| configuration_2/medium | Uz | 0.017645165 | 0.018336818 | 1.03919784 |
| configuration_2/medium | p | 0.13014477 | 0.13190209 | 1.01350283 |
| configuration_2/fine | Ux | 0.009989548 | 0.0065580818 | 0.65649435 |
| configuration_2/fine | Uy | 0.071567802 | 0.047019241 | 0.65698875 |
| configuration_2/fine | Uz | 0.01846577 | 0.013604684 | 0.73675149 |
| configuration_2/fine | p | 0.18481581 | 0.13921223 | 0.75324846 |
| configuration_3/coarse | Ux | 0.087341143 | 0.073702306 | 0.84384407 |
| configuration_3/coarse | Uy | 0.058624242 | 0.04875073 | 0.83157972 |
| configuration_3/coarse | Uz | 0.015156091 | 0.013951076 | 0.92049299 |
| configuration_3/coarse | p | 0.14901051 | 0.12731027 | 0.85437110 |
| configuration_3/medium | Ux | 0.14079677 | 0.12485354 | 0.88676423 |
| configuration_3/medium | Uy | 0.084227344 | 0.086699853 | 1.02935518 |
| configuration_3/medium | Uz | 0.021714323 | 0.021183192 | 0.97554007 |
| configuration_3/medium | p | 0.23268131 | 0.22712516 | 0.97612120 |
| configuration_3/fine | Ux | 0.16922314 | 0.14864881 | 0.87841896 |
| configuration_3/fine | Uy | 0.11008642 | 0.11103133 | 1.00858333 |
| configuration_3/fine | Uz | 0.020908501 | 0.018970348 | 0.90730314 |
| configuration_3/fine | p | 0.24770219 | 0.24564947 | 0.99171299 |

## Interpretation and limits

- 29 of 36 field trends have a tail/initial ratio below 1; 7 exceed 1. Ratios range from `0.135181` to `1.100045`. The direction is mixed across cases and fields.
- The separate logged terminal residual screen is `NOT_BELOW_TOLERANCE` for all 18 required `U` and `p` comparisons across the nine cases. A lower median ratio does not override this result; the `U` screen uses the largest logged component as a proxy and does not reproduce OpenFOAM internal vector `residualControl`.
- The flux-balance screen records nine diagnostic measurements but has no project acceptance criterion (`NOT_SET`).
- Every case remains `DIAGNOSTIC_ONLY`; family `scientific_validation` remains `BLOCKED`. The trend does not establish nonlinear convergence, mesh independence, model suitability, mass balance acceptance, independent execution, or measured cleanroom correlation.
- This report does not change case inputs, solver settings, tolerances, or acceptance criteria.
