# CleanroomX Parallel Workstream Report

- Worker ID: `WS-10-TESTING`
- Branch: `dev/WS-10-TESTING-20260926-dependency-history`
- Starting SHA: `2cccdbacff36e609cf9d39996cd36886bd574f35`
- Assigned scope: regression and integration hardening of project diagnostics/run-history freshness; production changes limited to defects proven by tests.
- Package version: `0.102.1`

## Baseline evidence

The immediately pre-merge project-diagnostics head `fc3e3155e6c78bc3e44fe9ca8bd532a9164a8fa1` passed GitHub Actions run `36194881564`.
The focused project-diagnostics gate reported **11 passed**.
The complete suite reported **1043 passed** on Python 3.11, 3.12, and 3.13. Windows launcher smoke, installed-wheel checks, representative CLI smoke, and Python 3.13 Tk/Xvfb GUI smoke also completed successfully.

## Defect fixed

Project diagnostics previously stopped at the newest retained run matching the current analysis kind/input and only then checked external-dependency freshness. If a file-backed dependency changed, a newer run was retained, and the dependency was later restored byte-for-byte to an older retained revision, diagnostics falsely reported stale dependency evidence even though an older retained same-input run exactly matched the current dependency content.

The selector now scans retained same-input runs newest-to-oldest and accepts the newest run whose external dependencies are current. It reports `run_history.external_dependency_stale` only when same-input retained evidence exists but **none** of those retained dependency revisions match current files.

## Files intentionally modified

- `src/cleanroomx/project_diagnostics.py`
- `tests/test_project_diagnostics.py`
- `CHANGELOG.md`
- this report

## Tests added

- restored external-dependency revision regression: two same-input retained runs at different dependency byte revisions, followed by restoration of the older dependency revision; diagnostics must accept the matching older evidence and return a clean project result.

## Compatibility

- No project schema change.
- No application/package version bump.
- No solver equation, tolerance, convergence, unit, or engineering acceptance change.
- No persisted run-history format change.
- Existing retained evidence remains valid.
- Selection remains deterministic: newest matching/current retained run wins.

## Shared interfaces changed

None. The public diagnostics result schema and CLI contracts are unchanged.

## Recommended integration order

This is a localized follow-up to the merged project-diagnostics work and can be integrated independently after CI passes. No other workstream should need rebasing solely for this change unless it also modifies `project_diagnostics.py` or `tests/test_project_diagnostics.py`.

## Verification status

Post-change GitHub Actions CI is required. Final PR head and exact post-change counts should be taken from the workstream PR before merge.
