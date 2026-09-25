# CleanroomX Project Migrations

## Current schema

CleanroomX v0.100.0 writes desktop projects using:

- schema: `cleanroomx.project`
- schema version: `1`
- application version: the installed CleanroomX version

The implementation is in `src/cleanroomx/project.py`.

## Supported legacy migrations

The loader currently migrates two legacy shapes into schema version 1:

1. `cleanroomx.project` schema version 0 containing a single `analysis` object.
2. A legacy single-analysis object with top-level `analysis_type` and `input` fields and no `schema` field.

Both are converted in memory to the current project model with one analysis and an active-analysis id.

## Rejection rules

The loader rejects malformed JSON, non-finite JSON constants such as `NaN` and `Infinity`, unexpected schemas, non-integer schema versions, unsupported future/older schema versions after known migration, unsupported analysis kinds, non-object analysis inputs, duplicate analysis ids, and invalid active-analysis references.

Unknown future project formats are rejected rather than silently reinterpreted.

## Migration provenance and protected first save

Supported migrations now return explicit immutable provenance alongside the validated current-schema project model. The migration record identifies the source format, source schema version when one exists, target schema version, and the deterministic migration step that ran. Existing callers of `project_from_dict()`, `load_project_document()`, and `load_project_document_with_revision()` retain their historical return types; migration-aware callers use the additive `*_with_migration_info` APIs.

The desktop treats a migrated legacy project as an unsaved converted copy. The source path remains available only as the engineering path context and as the protected legacy source. **Save Project** routes to **Save Project As**, and the first Save As refuses the original legacy path. A successful Save As writes schema version 1 to a different file before the migration protection is cleared. Closing without saving leaves the original legacy bytes unchanged.

This protection makes rollback explicit: the pre-migration source remains available for comparison or use with an older CleanroomX version. CleanroomX still does not synthesize reverse migrations.


## v0.100 path-context behavior

Project schema version remains **1**. v0.100 does not introduce a schema migration. When a project is saved into a different directory, relative consistency/dossier file references are rebased so they continue to identify the same external files. Imported consistency/dossier JSON is rebased from the source JSON directory into the current project context; when no project base exists, relative references are converted to absolute paths. Cached analysis results are cleared when **Save Project As** changes the project base directory.
