# CleanroomX sync-vtk v3 snapshot analysis

## Supported workflow

The solver-result analysis adapter accepts a result directory produced by the
`sync-vtk` command, provided that its `sync-state.json` and immutable
`snapshots/*.json` records remain available and the original VTK source tree
recorded in the state file is still present.

Example sequence:

1. Run `cleanroomx-cfd-pipeline sync-vtk` against the `foamToVTK` output tree,
   with a stable simulation ID and a configuration file.
2. Repeat the `--once` scan until the report shows imported snapshots; the
   stability window deliberately prevents reading a file while the solver is
   still writing it.
3. Open the snapshot-store directory in the solver-result explorer, or run:

   ```bash
   cleanroomx-cfd-pipeline analyze-results <snapshot-store> --simulation-id <run-id> --output <new-export-directory>
   ```

The export directory must be new and outside both the snapshot store and its
original VTK source tree.

## Integrity checks

For each imported record, CleanroomX checks:

- the v3 state schema and simulation/configuration/field-map identity;
- the deterministic snapshot path, snapshot SHA-256 and recorded byte size;
- the source VTK file's SHA-256 and byte size;
- the snapshot's `fields_sha256`, field count, case/time identity and
  `scientific_validation: BLOCKED` boundary;
- reconstruction of the explicit field-map declaration from recorded available
  and unavailable arrays;
- a fresh VTK import whose field payload hash matches the accepted snapshot.

The analysis exposes volume-weighted speed and velocity components, plus
additional scalar/vector fields whose semantics and units were explicitly
recorded. Missing mapped fields remain `not_available`; a field is not
synthesized to fill a gap.

## What this does not prove

The `sync-vtk` store is not a native OpenFOAM execution receipt. It does not
bind the original OpenFOAM time/field files, solver return code, solver log,
`checkMesh` output, convergence criteria, or independent cleanroom measurements.
Consequently, native-field verification, solver-log diagnostics, per-room
airflow/ACH, and physical validation remain unavailable or `BLOCKED`.

The original VTK source tree must remain accessible because v3 snapshots store
cell values and volume data but not the cell-center geometry required for
spatial views. Local hash-link consistency is not a digital signature and does
not establish authenticity. The regression fixtures are synthetic and do not
execute OpenFOAM.
