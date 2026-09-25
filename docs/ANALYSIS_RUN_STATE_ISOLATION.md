# Background Analysis State Isolation

CleanroomX executes engineering analyses on a background worker so the Tk desktop stays responsive. A completed worker result is valid only for the exact project/analysis execution context that launched it.

## Invariant

At launch, the desktop captures an immutable run-context record containing:

- the in-memory project object identity;
- active analysis ID and analysis kind;
- a deep-copied analysis-input snapshot;
- the normalized base directory used to resolve relative external references.

When the worker finishes, the UI accepts the result only when all of those values still match the current project state. If the project was replaced, the active analysis changed, the analysis input changed, or the base directory changed, the completion is discarded and the operator is told to validate and run again.

This is deliberately fail-closed. A stale worker result is never inserted into the per-analysis result cache or rendered as the current engineering result.

## Project-context mutation barriers

While an analysis is running:

- **Save Project As** is blocked because changing project location can rebase relative file references and therefore changes execution context.
- **Recovery Center** restoration is blocked because it can replace the complete project document.
- direct recovery restoration and direct project loading APIs reject replacement attempts.

Ordinary **Save Project** remains available for an already-saved project because it does not change the run base directory or the analysis input while the editor is locked.

The existing **Abandon Run** action remains non-preemptive: the backend worker is allowed to exit normally, but its result is ignored. A new run is not enabled until that worker has finished.

## Why object identity is part of the context

Two different project documents can contain the same analysis ID, kind, input JSON, active selection, and path. Content-only comparison would therefore allow a result from an old project object to be attached to a newly restored or reloaded project. The project-object token prevents that association.

This token is process-local only. It is not persisted, exported, or used as engineering provenance.

## Compatibility

This change does not modify:

- the CleanroomX project schema;
- saved project bytes;
- engineering solver equations or tolerances;
- analysis registry APIs;
- result JSON/report formats;
- autosave/recovery artifact formats.

## Regression coverage

Focused tests in `tests/test_gui.py` cover:

- matching run contexts being accepted;
- input, active-analysis, base-directory, and project-replacement mismatches being detected;
- stale worker completions being discarded;
- Save As and Recovery Center being blocked during an active run;
- direct project replacement APIs refusing mutation during a run.

The repository CI also runs the complete test suite on Python 3.11, 3.12, and 3.13, wheel/install checks, representative CLI smoke tests, and the installed Tk/Xvfb desktop smoke on Python 3.13.
