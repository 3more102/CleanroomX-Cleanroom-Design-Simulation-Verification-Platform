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

The loader rejects malformed JSON, non-finite JSON constants such as `NaN` and `Infinity`, unexpected schemas, non-integer schema versions, unsupported future/older schema versions after known migration, unsupported analysis kinds, non-object analysis inputs, duplicate analysis ids, and invalid active-analysis references. When `project.metadata.spatial_layout` is present, spatial layout version 1 is also validated for stable room/device IDs, finite geometry, positive room dimensions, supported device types, and valid device-to-room references.

Unknown future project formats are rejected rather than silently reinterpreted.

## Save behavior after migration

Loading a supported legacy file does not overwrite it automatically. If the migrated project is saved, CleanroomX writes schema version 1 using the current document model. Saving is validated first and uses an atomic temporary-file replacement.

For controlled archival workflows, retain a copy of the original legacy file before saving the migrated project.


## v0.100 path-context behavior

Project schema version remains **1**. v0.100 does not introduce a schema migration. When a project is saved into a different directory, relative consistency/dossier file references are rebased so they continue to identify the same external files. Imported consistency/dossier JSON is rebased from the source JSON directory into the current project context; when no project base exists, relative references are converted to absolute paths. Cached analysis results are cleared when **Save Project As** changes the project base directory.


## Spatial metadata compatibility

Project schema version remains **1**. The spatial layout is a versioned sub-document under `project.metadata.spatial_layout`; the supported spatial layout version is currently **1**. Valid spatial v1 data requires no migration and retains its existing stable IDs. Spatial metadata with an unsupported version or malformed identity/reference/geometry data is rejected rather than silently repaired during project load. Projects that do not contain spatial metadata are unaffected and may still seed a layout from compatible verification-analysis room geometry in the desktop workspace.
