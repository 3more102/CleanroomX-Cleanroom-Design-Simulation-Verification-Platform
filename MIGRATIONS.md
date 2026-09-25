# CleanroomX Project Migrations

## Current schema

CleanroomX v0.102.0 writes desktop projects using:

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

## Additive-field round-trip contract

Within supported schema version 1, fields that this CleanroomX build does not interpret are preserved as opaque strict-JSON data when a project is opened, edited, and saved. Preservation applies to unknown fields at the document top level, inside the `project` block, and inside individual analysis records. Known CleanroomX fields remain authoritative and cannot be overridden by an opaque extension field with the same key.

The same preservation rule is applied during supported legacy migration where an unconsumed source field has a lossless schema-v1 destination. The explicit schema-v0 shape carries unconsumed top-level and analysis fields forward. The older pre-schema single-analysis shape carries unconsumed top-level fields forward without reinterpreting them as current project metadata. CleanroomX does not interpret, validate the domain meaning of, or update opaque extension content beyond the normal strict-JSON requirement; extensions that require incompatible semantics should use an appropriate schema/version contract rather than relying on an unknown field.

## Migration provenance and protected first save

Supported migrations expose immutable provenance alongside the validated current-schema project model: source format, source schema version when one exists, target schema version, and the deterministic migration step that ran. Existing `project_from_dict()`, `load_project_document()`, and `load_project_document_with_revision()` callers retain their historical return types; migration-aware callers use the additive `*_with_migration_info` APIs.

The desktop treats a migrated legacy project as an unsaved converted copy while retaining the legacy file only as path context and the protected migration source. **Save Project** routes to **Save Project As**, and the first Save As refuses the original legacy path. Migration protection is cleared only after a validated schema-v1 save succeeds at a different path. Closing without saving leaves the original legacy bytes unchanged.

This preserves an explicit rollback/comparison source. CleanroomX does not synthesize reverse migrations.


## v0.100 path-context behavior

Project schema version remains **1**. v0.100 does not introduce a schema migration. When a project is saved into a different directory, relative consistency/dossier file references are rebased so they continue to identify the same external files. Imported consistency/dossier JSON is rebased from the source JSON directory into the current project context; when no project base exists, relative references are converted to absolute paths. Cached analysis results are cleared when **Save Project As** changes the project base directory.
