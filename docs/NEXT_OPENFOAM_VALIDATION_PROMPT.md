# Next-step prompt: proceed when physical case data exist

Use this prompt for the next CleanroomX/OpenFOAM engineering pass:

> Continue on open PR #1311 and issue #1296. First inspect the [run 63 native-to-VTK patch-parity report](OPENFOAM_V10_RUN_38772855917_NATIVE_VTK_PATCH_PARITY.md), exact-head checks, and archived dictionaries, native fields, `phi`, solver logs, VTK files, and triage JSON.
>
> Native-to-VTK checks cover final-time U and kinematic-pressure p in the internal-cell datasets for nine synthetic cases: 47,304 cells, 141,912 velocity components, and 47,304 pressure values matched by explicit `cellID` mapping. Run 63 additionally checks 27 inlet/outlet/walls patch datasets: 13,608 faces, 40,824 U components, and 13,608 p values mapped by serialized face geometry. Both audits pass only their recorded float32/ASCII serialization bounds. Do not repeat these checks unless fixing a concrete regression, or expand them to other solver releases, field types, patch-condition families, regions, time-selection behavior, or physical models without evidence.
>
> The run 61 residual and flux findings are recorded in the report. All nine log-based `U`/`p` residual screens exceed their configured tolerances; the flux report has no project-defined acceptance criterion. These are observations, not a proven diagnosis. Do not modify the synthetic model speculatively.
>
> Do not change geometry, boundary conditions, solver schemes, residual tolerances, or acceptance thresholds to make the synthetic cases pass. Any proposed model change must be tied to verified case requirements and evidence; no project flow-balance criterion is currently defined. Keep all nine runs `DIAGNOSTIC_ONLY`, scientific validation `BLOCKED`, and GCI ineligible while residuals fail or quantities of interest are not shown stable.
>
> Physical validation cannot proceed without a real cleanroom case: verified dimensions/CAD; diffuser, filter, and exhaust properties; operating conditions; measured supply/extract flows and room pressure; particle concentration/decay where available; measurement uncertainty; and a reproducible provenance manifest. When those data are supplied, verify provenance and condition alignment, build the smallest representative case, and compare predictions against the measurements with uncertainty. If they remain unavailable, keep issue #1296 open and document the blocker without fabricating values or substituting synthetic data.
>
> Keep `OF10-UTILITY-foamToVTK` and `OF10-VTK-IMPORT` partial and retain complete counts at 0/192 native, 0/717 integration, and 0/21 validated cleanroom workflows. Select the next bounded gap from the pinned v10 matrix and require reproducible field- or utility-specific evidence. Run exact-head CI, CFD VTK Regression, and the Foundation v10 workflow when applicable. Keep PR #1311 open and unmerged pending scientific validation.
