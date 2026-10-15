# Next-step prompt: physical OpenFOAM validation

Use this prompt for the next CleanroomX/OpenFOAM engineering pass:

> Continue the CleanroomX/OpenFOAM work from the open PR #1310 and issue #1296. First inspect the current repository state and the latest OpenFOAM Foundation v10 triage report. The latest synthetic run completed all nine cases and all 27 OpenFOAM commands, but its 18 terminal U/p residual comparisons remain above their configured tolerances. Treat `DIAGNOSTIC_ONLY`, byte-identical inputs, `Mesh OK.`, and process exit code 0 as execution evidence only. Scientific validation remains `BLOCKED`.
>
> Work toward a physically reviewable case using measured project inputs. Inspect the generated inlet and outlet patches, their areas and normals, specified supply and exhaust flows, room geometry, obstacles and filters, units, wall conditions, and the current steady laminar model assumptions. Check that the boundary conditions produce the intended mass flow. Use repository evidence and authoritative OpenFOAM Foundation v10 documentation for solver behavior; cite sources for any newly researched claims.
>
> Do not invent geometry, flow data, acceptance limits, measurements, or solver settings. Do not relax residual tolerances to make a screen pass. If required design or measurement data is absent, record exactly which input is missing and continue with independent checks that do not depend on it. Identify a justified solver/model change only after the current dictionaries and flux behavior have been reviewed.
>
> After any justified change, run `blockMesh`, `checkMesh`, and `simpleFoam` on coarse, medium, and fine meshes for all three configurations. Preserve complete logs and input hashes. Review residual histories, continuity and inlet/outlet flux balance, and stable quantities of interest. Export the required cell fields from the actual solver runs and use the existing three-grid VTK/GCI screening only when all grids have comparable, converged inputs and quantities. Compare eligible results against measured cleanroom data with uncertainty before changing `scientific_validation` from `BLOCKED`.
>
> Report execution success separately from solver convergence, mesh-independence evidence, physical validation, and any CleanroomX/OpenFOAM compatibility percentage. Provide a concise evidence-backed report, update issue #1296 and the relevant repository docs, run the applicable tests and actual Foundation v10 workflow, and save the result on a reviewable GitHub branch/PR. Leave the PR unmerged.
