# Next-step prompt: verify OpenFOAM field parity

Use this prompt for the next CleanroomX/OpenFOAM engineering pass:

> Continue work on open PR #1311 and issue #1296. Start by inspecting the current branch head, the permanent [run 56 VTK export report](OPENFOAM_V10_RUN_38680418943_VTK_EXPORT.md), and its linked receipt, native OpenFOAM fields, VTK outputs, and triage JSON.
>
> Run 56 completed all 36 OpenFOAM command stages across nine synthetic cases. CleanroomX imported all nine final-time cell-`U` VTK datasets, checked positive volumes, cell counts and SHA-256 values, and the downloaded artifact was independently rechecked. The report records the hashes. The run remains `DIAGNOSTIC_ONLY`: all nine `U` and all nine `p` log-based terminal residual comparisons are above their displayed tolerances; flux imbalance has no project acceptance criterion; configuration 1 has reverse outlet flow at each grid level. Scientific validation is `BLOCKED`.
>
> The next narrow task is a numerical field-parity check between each exported VTK cell-`U` array and the corresponding final-time OpenFOAM field. Inspect the native case output and Foundation v10 export behavior first. Establish cell correspondence and ordering from evidence; do not assume array ordering. Compare all three velocity components and report the numeric error and precision/tolerance basis. If correspondence cannot be demonstrated, state that limitation and leave the parity check unresolved. Add regression coverage that uses actual Foundation v10 VTK output or a faithful, independently verified fixture.
>
> Keep the two capability rows `OF10-UTILITY-foamToVTK` and `OF10-VTK-IMPORT` partial until field parity and the remaining scope are independently verified. Do not alter complete counts based solely on successful process execution or synthetic data.
>
> Do not run or present GCI as eligible while the terminal residual screens fail or quantities of interest are not shown stable. Do not relax tolerances or invent a flow-balance threshold. Any solver, geometry, or boundary-condition change must be tied to evidence from the current dictionaries, actual patch fluxes, and official OpenFOAM Foundation v10 sources.
>
> Keep the synthetic run separate from a physical cleanroom case. List missing project inputs such as verified dimensions/CAD, diffuser and filter properties, supply/exhaust measurements, operating conditions, and measured airflow/pressure/particle data with uncertainty. Do not claim physical validation without those inputs and an accepted comparison.
>
> Update the relevant tests and docs, rerun CI and the Foundation v10 workflow when its path filters apply, add exact run/artifact identifiers and hashes to the PR, and save the changes on the existing branch. Leave PR #1311 open and unmerged.
