# Rollback Procedure

## Code rollback

For the shared repository, prefer a Git revert of the release-changing commit or merge rather than rewriting shared history.

Before rollback:

1. Record the current commit SHA and CI run.
2. Preserve affected project files and exported reports.
3. Identify the last known validated CleanroomX baseline.
4. Revert the required release commit(s) through normal review/CI.
5. Run the full CI matrix and representative GUI/CLI smoke checks before declaring the rollback complete.

Do not force-reset shared `main` unless repository policy explicitly permits it and collaborators understand the history rewrite.

## Project-file rollback

Schema version 1 is the current desktop project format. Supported legacy formats are migrated in memory on load. The desktop treats the converted state as unsaved and requires the first save to use a different path, so the original legacy file remains unchanged for rollback or comparison.

If a migrated project must return to its original legacy representation, reopen the preserved legacy source with a compatible CleanroomX version. CleanroomX does not synthesize reverse migrations to historical legacy shapes.

## Result rollback

Generated JSON/Markdown results are derived artifacts. If the application version changes, regenerate results from preserved source inputs using the selected validated version rather than editing generated evidence by hand.

## Acceptance

A rollback is complete only when the selected baseline installs successfully, its CI/regression checks pass, and required project files can be opened and validated with that baseline.


## v0.100 release anchor

The validated v0.100.0 merge commit is `fa02c71f990790089cb9c64eb2e009cd984eb5db`. Its exact PR head `d8965090ee86713919079d9ee5e8a3b1d8f95e3b` passed CI run #822 before merge. Use repository history and normal revert/CI flow rather than rewriting shared history.
