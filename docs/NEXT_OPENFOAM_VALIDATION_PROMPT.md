# Next-step prompt: validate OpenFOAM VTK evidence

Use this prompt for the next CleanroomX/OpenFOAM engineering pass:

> Continue the CleanroomX/OpenFOAM work on open PR #1311 and issue #1296. Inspect the current PR head, latest Foundation v10 workflow run, run logs, execution receipt, triage JSON, and uploaded artifacts before changing anything.
>
> The nine-case synthetic workflow now executes `blockMesh`, `checkMesh`, `simpleFoam`, and `foamToVTK` for each case. It exports final-time cell `U`, imports each generated VTK, checks its cell count against the bound family manifest, and records a SHA-256. Confirm all nine paths, digests, cell counts, command stages, and Foundation v10 build identity from the actual latest artifact. If any check or the workflow failed, diagnose the exact failure and repair it before adding further claims.
>
> Treat this as execution and data-ingestion evidence only. It does not establish residual or nonlinear convergence, mass-balance acceptance, mesh independence, physical accuracy, or a validated CleanroomX/OpenFOAM workflow. Review terminal residual screens and signed final-time `phi` fluxes separately. Do not invent or relax a project acceptance criterion.
>
> Do not run or present GCI as eligible until the same configuration's coarse, medium, and fine solutions have comparable inputs, stable quantities of interest, and justified convergence evidence. The current automated export contains velocity `U` only; it does not solve or export contaminant transport, and it does not substitute for measured cleanroom correlation.
>
> Work toward a physically reviewable case using project-supplied dimensions, CAD/IFC geometry, inlet and exhaust data, filter/diffuser details, operating conditions, and measured cleanroom data with uncertainty. Record each missing input explicitly and continue with independent checks that do not depend on it. Use repository evidence and official OpenFOAM Foundation v10 documentation for solver behavior, citing new research.
>
> Update the relevant docs and evidence-backed capability rows only after the latest workflow run is complete. Keep partial evidence partial and preserve the current complete-count and validation gates unless the repository's defined criteria are actually met. Run the applicable tests and workflows, update the PR description with the exact run and artifact identifiers plus SHA-256, and commit the work to the existing reviewable branch. Leave the PR open and unmerged.
