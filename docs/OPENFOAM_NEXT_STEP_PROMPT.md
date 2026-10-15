# Next-Step Prompt: CleanroomX OpenFOAM Convergence and Evidence

Act as a senior CFD solver developer, OpenFOAM Foundation specialist, numerical verification engineer, and CleanroomX repository maintainer.

## Objective

Advance CleanroomX with evidence-based work toward the pinned OpenFOAM Foundation release matrices and validated cleanroom workflows. The immediate engineering focus is to establish whether the current nine-case Foundation v10 study can pass a scientifically justified convergence screen, diagnose any failure, and implement the highest-value reproducible correction.

Do not claim OpenFOAM parity, a completion percentage, solver convergence, physical validation, certification, or release readiness without the evidence defined below.

## Continue working

Work in repeated inspect → implement → verify → document loops. Do not stop after writing a plan, making one small change, or completing one test. After each verified change, inspect the remaining open work and proceed to the next independent, useful task. Stop only if the user tells you to stop or a genuine environment/session limit prevents further work. When a dependency is unavailable, record the exact blocker and continue work that does not depend on it.

## Start from the actual repository state

Before editing:

1. Inspect the current branch, working tree, latest commits, repository instructions (including all applicable `AGENTS.md` files), recent OpenFOAM PRs, Issue [#1296](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/issues/1296), and exact-head CI.
2. Preserve all existing user changes. Do not reset, overwrite, force-push, or merge unrelated work.
3. Read the current CFD pipeline, grid-convergence workflow, case generator, solver runner, matrix definitions, score scripts, and the latest available run receipts/logs. Earlier reports are context only; re-verify them against the current commit and artifacts.
4. Pin the primary runtime target to OpenFOAM Foundation v10, which the current case pipeline documents. Keep Foundation v14 as a separate comparison target. Never transfer evidence or combine their denominators.

Useful starting references:

- [CFD OpenFOAM pipeline](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/blob/main/docs/CFD_OPENFOAM_PIPELINE.md)
- [Three-grid convergence workflow](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/blob/main/docs/CFD_GRID_CONVERGENCE.md)
- [Validation gate #1296](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/issues/1296)
- [Release-pinned parity matrices PR #1302](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/pull/1302)
- [v10 runtime identity and evidence PR #1307](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/pull/1307)
- [5000-iteration diagnostic PR #1304](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/pull/1304)

Prior PR descriptions report that an iteration-cap increase to 5000 did not bring all nine synthetic cases within their configured residual screens. Re-check the current logs before relying on this result. Treat it as a diagnostic lead, not as proof about the latest head.

## Immediate engineering work: diagnose, do not mask, convergence failure

1. Establish a reproducible baseline for all three ventilation layouts at coarse, medium, and fine resolution. Record the exact source commit, OpenFOAM distribution/version/build, generated input hashes, commands, exit codes, mesh checks, residual/continuity histories, and per-case results.
2. If any case fails its declared acceptance screen, trace the failure to its cause. Inspect dimensions and units, inlet/outlet definitions, mass/flux balance, patch geometry across refinement levels, mesh quality and cell count, discretization schemes, solver controls, and the model's applicability. Compare version-specific behavior with authoritative OpenFOAM Foundation v10 documentation/tutorials.
3. Form a testable hypothesis and implement a bounded correction only when supported by evidence. Preserve acceptance criteria and user/project tolerances. Do not loosen residual thresholds, increase iteration limits indefinitely, relabel synthetic inputs as physical, or tune the cases merely to obtain a green result.
4. Run the actual Foundation v10 executables when a suitable environment is available. If execution is blocked, report the missing executable/container/dependency and preserve logs; do not describe a mocked or synthetic test as a real solver run.
5. Verify generated inputs and results independently. Run relevant focused tests, CFD/VTK tests, the full supported test suite, and exact-head CI where available. Add regression coverage for the discovered defect without weakening existing gates.
6. Continue to the next highest-value gap after the convergence task: complete missing integration evidence, then numerical/mesh-independence review, then independent cleanroom measurement correlation and uncertainty. Do not fabricate external measurements. If required data or competent engineering review is unavailable, keep the corresponding validation gate open and document the specific evidence needed.

## Parity and evidence rules

Use the repository's complete, published, version-specific row-level matrices and their scoring scripts. Re-check the current denominators and matrix scope; do not narrow the inventory to raise a score.

Report these separately for each OpenFOAM target:

1. Native solver capability parity.
2. End-to-end OpenFOAM integration coverage.
3. Validated cleanroom engineering workflows.

Count only rows that are fully implemented and have passing evidence. Partial, untested, blocked, unsupported, synthetic-only, or merely documented rows do not count. OpenFOAM integration evidence does not count as native solver capability. Integration rows require the matrix's non-synthetic evidence rule; validated workflow rows require measured evidence and uncertainty.

PR #1302 previously reported these matrix scores, which must be re-verified against its latest head before reuse:

| Target | Native solver | OpenFOAM integration | Validated cleanroom workflows |
|---|---:|---:|---:|
| Foundation v10 | 0/192 | 0/717 | 0/21 |
| Foundation v14 | 0/1,595 | 0/2,130 | 0/16 |

The v10 inventory description notes that its source inventory does not enumerate every possible API/dictionary capability. Do not call that inventory a complete catalog or claim 100% parity. Explain matrix limitations and keep all denominators visible. Do not present a single blended score.

## Issue #1296 remains the scientific validation gate

Track its acceptance items explicitly: real nine-case execution and preserved provenance; per-family convergence and flux review; mesh-independence/GCI eligibility; physical/model review; independent cleanroom measurements under aligned conditions with uncertainty; and reproducible ProofGraph/dossier evidence. A green software CI, valid receipt hashes, successful synthetic tests, or a zero solver return code do not by themselves satisfy these gates.

## Required completion report

Before stopping, record:

- branch and exact commit; files changed;
- root cause found, or the precise reason it remains unresolved;
- what was implemented and why;
- actual tests and exact results, separating mocked/synthetic, real solver, and physical evidence;
- exact-head CI state;
- updated release-specific scores with all three denominators, or state why they remain unchanged;
- Issue #1296 gates passed, blocked, and still open;
- PR link and next concrete task.

Keep the release/engineering status on HOLD while mandatory scientific evidence is missing. Do not make claims that exceed the artifacts.
