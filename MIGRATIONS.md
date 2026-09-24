# CleanroomX Project Migrations

## Current schema

CleanroomX v0.99.0 writes desktop projects using:

- schema: `cleanroomx.project`
- schema version: `1`
- application version: the installed CleanroomX version

The implementation is in `src/cleanroomx/project.py`.

## Supported legacy migrations

The loader currently migrates two legacy shapes into schema version 1:

1. `cleanroomx.project` schema version 0 containing a single `analysis` object.
2. A legacy single-analysis object with top-level `analysis_type` and `input` fields and no `schema` field.

Both are converted in memory to the current project model with a single analysis and an active-analysis id.

## Rejection rules

The loader rejects:

- malformed JSON;
- non-finite JSON constants such as `NaN` and `Infinity`;
- an unexpected project schema;
- non-integer schema versions;
- future schema versions newer than the running application supports;
- unsupported older schema versions after the known migration step;
- unsupported analysis kinds;
- non-object analysis inputs;
- duplicate analysis ids;
- invalid active-analysis references.

CleanroomX does not silently reinterpret unknown future formats.

## Save behavior after migration

Loading a supported legacy file does not overwrite it automatically. If the migrated project is saved, CleanroomX writes schema version 1 using the current document model. Saving is validated first and uses an atomic temporary-file replacement.

For controlled archival workflows, retain a copy of the original legacy file before saving the migrated project.
