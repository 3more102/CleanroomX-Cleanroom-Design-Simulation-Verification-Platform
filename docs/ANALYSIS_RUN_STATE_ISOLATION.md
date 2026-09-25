# Background Analysis State Isolation

CleanroomX already binds completed analysis results to canonical submitted-input SHA-256 provenance and revalidates that provenance at cache restore, worker-success acceptance, and export boundaries. Background worker context isolation adds a separate guard for state that input provenance cannot identify.

## Completion invariant

At launch, the desktop retains a process-local run context containing:

- a strong reference to the originating `ProjectDocument`;
- a strong reference to the originating `AnalysisDocument`;
- the normalized project base directory used to resolve relative references.

A worker completion is accepted only while:

- the current project is the same project object;
- the originating analysis is still the active analysis and is still the same analysis object;
- the current normalized base directory matches the launch base directory.

This check runs before both worker errors and successful results are published. If the context changed, the completion is discarded and the operator is instructed to validate and run again. Successful results still pass the existing canonical input-provenance check afterward.

## Mutation barriers

While a backend worker is active:

- **Save Project As** is blocked because it can replace the in-memory project object and rebase relative file references.
- **Recovery Center** restoration is blocked because it replaces the complete project document and path context.
- direct project-loading and recovery-restoration methods reject replacement attempts.

The existing **Abandon Run** behavior remains non-preemptive: the UI marks the run abandoned and waits for the backend worker to exit; its completion is ignored. A new run is not enabled until that worker has finished.

Ordinary Save Project remains available for an already-saved project because it does not rebase the project context or mutate the locked analysis editor.

## Why object identity is required

Two different project documents can legitimately contain the same analysis ID, kind, and identical input JSON. The existing input-provenance hash therefore cannot distinguish an old worker from a replacement project that happens to contain identical analysis content. Strong object identity closes that gap without changing persisted formats.

The context record exists only in memory for the lifetime of the worker. It is not serialized and is not engineering provenance.

## Compatibility

No changes are made to:

- project schema version 1 or legacy migration behavior;
- autosave/recovery schemas;
- solver equations, numerical tolerances, convergence behavior, or acceptance criteria;
- application run/result/report formats;
- the existing canonical input-provenance freshness guard.

## Regression coverage

`tests/test_gui.py` covers replacement by an identical-content project, stale error completion after base-directory change, active-analysis reassignment, Save As/Recovery Center barriers, direct replacement APIs, and compatibility with the existing mid-run input-provenance freshness test. Repository CI provides the full Python 3.11/3.12/3.13 suite, wheel/install checks, CLI smoke checks, and the installed Tk/Xvfb GUI smoke.
