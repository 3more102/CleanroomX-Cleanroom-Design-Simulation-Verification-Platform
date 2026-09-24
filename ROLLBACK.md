# Rollback Procedure

## Code rollback

For a shared repository, prefer a Git revert of the release-changing commit or merge rather than rewriting shared history.

Before rollback:

1. Record the current commit SHA and CI run.
2. Preserve affected project files and exported reports.
3. Identify the last known validated CleanroomX baseline.
4. Revert the required release commit(s) through normal review/CI.
5. Run the full CI matrix and representative GUI/CLI smoke checks before declaring the rollback complete.

Do not use a force reset on shared `main` unless repository policy explicitly permits it and all collaborators understand the history rewrite.

## Project-file rollback

Schema version 1 is the current desktop project format. Supported legacy formats are migrated in memory on load and are rewritten as schema version 1 only when the operator saves the project. If a migrated project must be rolled back to its original legacy representation, restore the archived original file; CleanroomX does not synthesize a reverse migration to historical shapes.

## Generated results

Generated JSON/Markdown results are derived artifacts. If the application version changes, regenerate results from preserved source inputs using the selected validated version rather than editing generated evidence by hand.
