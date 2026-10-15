# Next-step prompt: proceed when physical case data exist

Use this prompt for the next CleanroomX/OpenFOAM engineering pass:

> Continue on open PR #1311 and issue #1296. First inspect the [run 58 native-to-VTK parity report](OPENFOAM_V10_RUN_38694132081_NATIVE_VTK_PARITY.md), exact-head checks, and archived dictionaries, native fields, `phi`, solver logs, VTK files, and triage JSON.
>
> The native-to-VTK check is complete for the nine synthetic cases: all 47,304 cells and 141,912 velocity components matched by the explicit `cellID` mapping within the recorded float32/ASCII serialization bounds. Do not repeat or expand that claim to other solver releases or physical models without evidence.
>
> The run 58 residual and flux findings are recorded in the report. All nine log-based `U`/`p` residual screens exceed their configured tolerances; configuration 1 has inward flux at its synthetic pressure outlet on all grids. These are observations, not a proven diagnosis. Do not repeat that analysis or modify the synthetic model speculatively.
>
> Do not change geometry, boundary conditions, solver schemes, residual tolerances, or acceptance thresholds to make the synthetic cases pass. Any proposed model change must be tied to verified case requirements and evidence; no project flow-balance criterion is currently defined. Keep all nine runs `DIAGNOSTIC_ONLY`, scientific validation `BLOCKED`, and GCI ineligible while residuals fail or quantities of interest are not shown stable.
>
> Physical validation cannot proceed without a real cleanroom case: verified dimensions/CAD; diffuser, filter, and exhaust properties; operating conditions; measured supply/extract flows and room pressure; particle concentration/decay where available; measurement uncertainty; and a reproducible provenance manifest. When those data are supplied, verify provenance and condition alignment, build the smallest representative case, and compare predictions against the measurements with uncertainty. If they remain unavailable, keep issue #1296 open and document the blocker without fabricating values or substituting synthetic data.
>
> Keep `OF10-UTILITY-foamToVTK` and `OF10-VTK-IMPORT` partial and retain complete counts at 0/192 native, 0/717 integration, and 0/21 validated cleanroom workflows. Update evidence, tests, and documentation only for reproducible findings. Run exact-head CI, CFD VTK Regression, and the Foundation v10 workflow when applicable. Keep PR #1311 open and unmerged pending scientific validation.
