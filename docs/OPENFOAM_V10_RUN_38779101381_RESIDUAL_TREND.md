# OpenFOAM Foundation v10 run 68 residual-trend diagnostic

## Provenance and scope

- Workflow run: [38779101381](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38779101381), OpenFOAM Foundation v10 grid execution run 68, on commit `469d897277463455819ba72d16cd2128340e0935`.
- Evidence artifact: [11994294543](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38779101381/artifacts/11994294543). The downloaded archive SHA-256 `f29c27fdb8170cf8dae77a509558619420a33a6e9ccfa0d8387693e4972c8668` matches the Actions artifact digest.
- The nine cases are synthetic rectangular layout/grid fixtures. This is a log diagnostic of that archive, not a physical cleanroom case or validation result.
- Reproduce against the extracted `cleanroomx-cfd-grid-family` directory with `cleanroomx-cfd-grid-triage <family-root> --window 5 --trend-window 50`.

## Method

For each logged field (`Ux`, `Uy`, `Uz`, `p`) in each case, the diagnostic compares the median of the first 50 logged initial linear residuals with the median of the last 50. Each log has 150 samples per field; the two 50-sample windows are disjoint. The reported ratio is `tail median / initial median`. It is descriptive and adds no pass/fail criterion.

## Results

| Case | Field | First-window median | Tail-window median | Tail / initial |
| --- | --- | ---: | ---: | ---: |
| configuration_1/coarse | Ux | 0.008516816454 | 0.008432738955 | 0.99012806 |
| configuration_1/coarse | Uy | 0.01136902342 | 0.0109790884 | 0.96570198 |
| configuration_1/coarse | Uz | 0.00694360876 | 0.006995095859 | 1.007415 |
| configuration_1/coarse | p | 0.0438572201 | 0.04251745991 | 0.96945178 |
| configuration_1/medium | Ux | 0.002898949523 | 0.0005043161363 | 0.17396513 |
| configuration_1/medium | Uy | 0.003414382265 | 0.0006647915225 | 0.19470331 |
| configuration_1/medium | Uz | 0.001966657654 | 0.0003032449827 | 0.15419307 |
| configuration_1/medium | p | 0.03519136165 | 0.004757203072 | 0.13518099 |
| configuration_1/fine | Ux | 0.01509081817 | 0.006176039801 | 0.40925812 |
| configuration_1/fine | Uy | 0.0161403217 | 0.008232193669 | 0.51003901 |
| configuration_1/fine | Uz | 0.008088665259 | 0.00435119859 | 0.53793777 |
| configuration_1/fine | p | 0.1854891459 | 0.08430875898 | 0.45452125 |
| configuration_2/coarse | Ux | 0.008326791026 | 0.008341995732 | 1.001826 |
| configuration_2/coarse | Uy | 0.02474738978 | 0.0221985898 | 0.89700732 |
| configuration_2/coarse | Uz | 0.01583372679 | 0.01505642618 | 0.95090855 |
| configuration_2/coarse | p | 0.07128105165 | 0.06422612327 | 0.9010266 |
| configuration_2/medium | Ux | 0.01036441444 | 0.01031251047 | 0.9949921 |
| configuration_2/medium | Uy | 0.04610519957 | 0.05071778506 | 1.1000448 |
| configuration_2/medium | Uz | 0.01764516532 | 0.01833681763 | 1.0391978 |
| configuration_2/medium | p | 0.1301447675 | 0.1319020896 | 1.0135028 |
| configuration_2/fine | Ux | 0.009989547979 | 0.006558081806 | 0.65649435 |
| configuration_2/fine | Uy | 0.07156780174 | 0.04701924051 | 0.65698875 |
| configuration_2/fine | Uz | 0.01846577025 | 0.01360468379 | 0.73675149 |
| configuration_2/fine | p | 0.1848158132 | 0.1392122259 | 0.75324846 |
| configuration_3/coarse | Ux | 0.08734114312 | 0.07370230572 | 0.84384407 |
| configuration_3/coarse | Uy | 0.05862424161 | 0.04875073015 | 0.83157972 |
| configuration_3/coarse | Uz | 0.01515609106 | 0.01395107553 | 0.92049299 |
| configuration_3/coarse | p | 0.1490105061 | 0.1273102703 | 0.8543711 |
| configuration_3/medium | Ux | 0.1407967682 | 0.1248535371 | 0.88676423 |
| configuration_3/medium | Uy | 0.08422734408 | 0.08669985297 | 1.0293552 |
| configuration_3/medium | Uz | 0.02171432296 | 0.02118319205 | 0.97554007 |
| configuration_3/medium | p | 0.2326813054 | 0.2271251552 | 0.9761212 |
| configuration_3/fine | Ux | 0.1692231353 | 0.148648811 | 0.87841896 |
| configuration_3/fine | Uy | 0.1100864179 | 0.111031326 | 1.0085833 |
| configuration_3/fine | Uz | 0.02090850056 | 0.01897034812 | 0.90730314 |
| configuration_3/fine | p | 0.2477021851 | 0.2456494735 | 0.99171299 |

## Interpretation and limits

- 29 of 36 field ratios are below 1 and 7 exceed 1. Ratios range from `0.135181` to `1.100045`; direction is mixed across cases and fields.
- The separate logged terminal residual screen is `NOT_BELOW_TOLERANCE` for all 18 required `U` and `p` comparisons across the nine cases. A lower median ratio does not override this result; the `U` screen uses the largest logged component as a proxy and does not reproduce OpenFOAM's internal vector `residualControl` calculation.
- Final-time flux imbalance measurements span `0.005341335563%` to `0.1871453292%`; the project has no flow-balance acceptance criterion (`NOT_SET`).
- Every case remains `DIAGNOSTIC_ONLY`; family `scientific_validation` remains `BLOCKED`. These results do not establish nonlinear convergence, mesh independence, model suitability, mass-balance acceptance, independent execution, or measured cleanroom correlation.
- This report does not change case inputs, solver settings, tolerances, or acceptance criteria.
