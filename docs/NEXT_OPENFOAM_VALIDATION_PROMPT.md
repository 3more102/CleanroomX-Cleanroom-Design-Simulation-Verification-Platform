# Next-step prompt: diagnose numerical results and physical-data gaps

Use this prompt for the next CleanroomX/OpenFOAM engineering pass:

> Continue on open PR #1311 and issue #1296. First inspect the [run 58 native-to-VTK parity report](OPENFOAM_V10_RUN_38694132081_NATIVE_VTK_PARITY.md), exact-head checks, and archived dictionaries, native fields, `phi`, solver logs, VTK files, and triage JSON.
>
> The native-to-VTK check is complete for the nine synthetic cases: all 47,304 cells and 141,912 velocity components matched by the explicit `cellID` mapping within the recorded float32/ASCII serialization bounds. Do not repeat or expand that claim to other solver releases or physical models without evidence.
>
> The next narrow task is a diagnostic review of the run 58 residual and flux findings. Compare the generated `system/fvSolution`, `system/fvSchemes`, `system/controlDict`, boundary dictionaries, mesh patch geometry, terminal `U`/`p` residual-control screens, signed outlet fluxes, and grid-level quantities. Separate observed facts from possible causes. Check relevant OpenFOAM Foundation v10 primary documentation/source before describing solver behavior.
>
> Do not change geometry, boundary conditions, solver schemes, residual tolerances, or acceptance thresholds to make the synthetic cases pass. Any proposed model change must be tied to verified case requirements and evidence; no project flow-balance criterion is currently defined. Keep all nine runs `DIAGNOSTIC_ONLY`, scientific validation `BLOCKED`, and GCI ineligible while residuals fail or quantities of interest are not shown stable.
>
> Physical validation cannot proceed without a real cleanroom case: verified dimensions/CAD; diffuser, filter, and exhaust properties; operating conditions; measured supply/extract flows and room pressure; particle concentration/decay where available; measurement uncertainty; and a reproducible provenance manifest. If those data are unavailable, document the exact inputs and independent measurements needed without fabricating values.
>
> Keep `OF10-UTILITY-foamToVTK` and `OF10-VTK-IMPORT` partial and retain complete counts at 0/192 native, 0/717 integration, and 0/21 validated cleanroom workflows. Update evidence, tests, and documentation only for reproducible findings. Run exact-head CI, CFD VTK Regression, and the Foundation v10 workflow when applicable. Keep PR #1311 open and unmerged pending scientific validation.
