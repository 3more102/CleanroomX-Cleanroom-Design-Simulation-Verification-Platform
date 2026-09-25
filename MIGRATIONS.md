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

## Save behavior after migration

Loading a supported legacy file does not overwrite it automatically. If the migrated project is saved, CleanroomX writes schema version 1 using the current document model. Saving is validated first and uses an atomic temporary-file replacement.

For controlled archival workflows, retain a copy of the original legacy file before saving the migrated project.


## v0.100 path-context behavior

Project schema version remains **1**. v0.100 does not introduce a schema migration. When a project is saved into a different directory, relative consistency/dossier file references are rebased so they continue to identify the same external files. Imported consistency/dossier JSON is rebased from the source JSON directory into the current project context; when no project base exists, relative references are converted to absolute paths. Cached analysis results are cleared when **Save Project As** changes the project base directory.

## Recovery artifact compatibility

Recovery autosaves use a separate `cleanroomx.autosave` envelope and do not change the `.cleanroomx.json` project schema.

New recovery writes use recovery schema version **2**. Version 2 adds a canonical SHA-256 integrity block covering the complete recovery payload except the integrity block itself. CleanroomX verifies that digest whenever the artifact is loaded and reopens a just-written artifact before rotating older recovery generations. A structurally valid version-2 file whose content no longer matches its digest is rejected and preserved as a recovery scan issue.

Recovery schema version **1** remains readable for backward compatibility. Because version 1 had no embedded self-integrity digest, the Recovery Center labels it **legacy/unverified** rather than claiming checksum verification. Restoring either supported recovery version still passes the embedded project snapshot through the ordinary project-schema validator.

The recovery SHA-256 detects accidental or unexplained content changes; it is not a keyed signature and does not establish source authenticity against an actor able to rewrite both content and digest.

