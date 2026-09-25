# CleanroomX Project Migrations

## Current schema

CleanroomX v0.100.0 writes desktop projects using:

- schema: `cleanroomx.project`
- schema version: `1`
- application version: the installed CleanroomX version
- optional-on-read / mandatory-on-new-save `integrity` record with canonical SHA-256 content identity

The implementation is in `src/cleanroomx/project.py`. Existing schema-version-1 projects written before integrity hardening remain valid and acquire the integrity record on their next save.

## Supported legacy migrations

The loader currently migrates two legacy shapes into schema version 1:

1. `cleanroomx.project` schema version 0 containing a single `analysis` object.
2. A legacy single-analysis object with top-level `analysis_type` and `input` fields and no `schema` field.

Both are converted in memory to the current project model with one analysis and an active-analysis id.

## Rejection rules

The loader rejects malformed JSON, non-finite JSON constants such as `NaN` and `Infinity`, unexpected schemas, non-integer schema versions, unsupported future/older schema versions after known migration, unsupported analysis kinds, non-object analysis inputs, duplicate analysis ids, invalid active-analysis references, malformed/unsupported integrity metadata, and SHA-256 integrity mismatches.

Unknown future project formats are rejected rather than silently reinterpreted.

## Save behavior after migration

Loading a supported legacy file does not overwrite it automatically. If the migrated project is saved, CleanroomX writes schema version 1 using the current document model and adds the canonical integrity record. Saving is validated first, uses same-directory atomic replacement with fsync durability where supported, and is accepted only after a stable strict-loader read-back verification. GUI saves additionally retain external-revision conflict protection.

For controlled archival workflows, retain a copy of the original legacy file before saving the migrated project.


## v0.100 path-context behavior

Project schema version remains **1**. v0.100 does not introduce a schema migration. When a project is saved into a different directory, relative consistency/dossier file references are rebased so they continue to identify the same external files. Imported consistency/dossier JSON is rebased from the source JSON directory into the current project context; when no project base exists, relative references are converted to absolute paths. Cached analysis results are cleared when **Save Project As** changes the project base directory.
