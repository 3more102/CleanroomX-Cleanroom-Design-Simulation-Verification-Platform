# BIM / IFC semantic interoperability

CleanroomX includes an optional IFC semantic bridge in `cleanroomx.bim_ifc`.

The bridge is deliberately separated from the engineering solvers. It converts IFC
spaces and selected building-services/equipment entities into the existing
CleanroomX spatial layout contract, then records provenance linking the imported
layout to both the original IFC file and the normalized semantic data.

## Current scope

The importer currently supports:

- `IfcSpace` -> CleanroomX room
- `IfcDoor` -> door
- `IfcWindow` -> window
- `IfcAirTerminal` / `IfcFlowTerminal` -> supply, return, or exhaust where the
  IFC predefined type identifies the airflow role
- `IfcSensor` -> sensor
- `IfcFlowController`, `IfcUnitaryEquipment`, `IfcFan`, `IfcPump`, and
  `IfcFurnishingElement` -> equipment
- IFC unit scaling to metres through IfcOpenShell
- nested local-placement translation origins
- space Length / Width / Height base quantities
- containment links from supported devices to `IfcSpace`
- deterministic normalized semantic records
- duplicate `GlobalId` and dangling-space rejection
- semantic SHA-256 and original IFC source SHA-256 provenance

The base CleanroomX installation still has no mandatory third-party runtime
dependencies. Install the optional BIM dependency to read native `.ifc` files:

```bash
pip install "cleanroomx[bim]"
```

## CLI workflow

Native IFC ingestion is also available through the installed `cleanroomx-ifc`
command:

```bash
cleanroomx-ifc import project.cleanroomx.json facility.ifc
cleanroomx-ifc plan project.cleanroomx.json facility-v2.ifc
cleanroomx-ifc reimport project.cleanroomx.json facility-v2.ifc
```

The initial `import` refuses to overwrite existing unlinked `spatial_layout`
metadata unless `--replace-existing-layout` is supplied. It never resets an
existing IFC identity link; linked projects must use `plan` and `reimport`.

`plan` is read-only and returns exit code 0 when the candidate can be applied,
1 when conflicts or spatial validation block application, and 2 for operational
or input errors. `reimport` applies only conflict-free candidates. Mutating
commands use the project revision guard and persistent save lock, so an external
project edit between load and save is rejected instead of overwritten. Successful
JSON output includes the IFC source digest plus the project revision digest before
and after the write.

## Desktop workflow

The desktop application exposes the same identity-preserving IFC workflow from the
**BIM** menu:

- **Import IFC Spatial Layout...** establishes the first IFC identity baseline;
- **Review IFC Re-import...** opens a read-only per-entity change plan;
- **Apply IFC Re-import...** applies only a conflict-free reviewed candidate.

The review window shows each IFC `GlobalId`, the mapped CleanroomX spatial ID,
the planned action, and whether the local project and IFC source changed relative
to the prior import baseline. A two-sided divergent edit blocks application.

Initial desktop import presents the extracted source name, room/device counts, and
exact IFC source SHA-256 before any project mutation. The same confirmation is used
when an existing unlinked spatial layout would be replaced.

For both accepted initial import and accepted re-import, the desktop immediately
re-reads the selected IFC source before mutating the project and requires both the
raw source SHA-256 and normalized semantic SHA-256 to match the reviewed candidate.
If either digest changed during the review-to-apply window, the operation fails
closed and leaves the project unchanged.

Import and re-import modify the in-memory project only; the normal CleanroomX Save
command remains responsible for persistence, so existing external-revision checks,
save locking, revision history, and recovery behavior remain authoritative. IFC
operations do not silently synchronize engineering analysis inputs.

## API

```python
from cleanroomx.bim_ifc import (
    apply_ifc_semantics_to_project,
    extract_ifc_semantics,
    plan_ifc_semantic_reimport,
    reimport_ifc_semantics_to_project,
)

semantics, provenance = extract_ifc_semantics("facility.ifc")
apply_ifc_semantics_to_project(
    project,
    semantics,
    source_name=provenance["source_name"],
    source_sha256=provenance["source_sha256"],
)
```

The resulting project receives:

- `project.metadata["spatial_layout"]`: validated CleanroomX spatial data
- `project.metadata["ifc_link"]`: source file name, source SHA-256, normalized
  semantic SHA-256, imported room/device counts, and tamper-evident element
  bindings from IFC `GlobalId` values to stable CleanroomX spatial IDs

The link schema is version 2. Its per-element bindings include the source semantic
record digest and source-derived spatial-object digest. A canonical
`bindings_sha256` protects the identity table against silent metadata edits.

## Conflict-aware re-import

After an initial schema-v2 import, a later IFC revision can be reviewed before any
project mutation:

```python
plan = plan_ifc_semantic_reimport(
    project,
    revised_semantics,
    source_name="facility-v2.ifc",
    source_sha256=revised_source_sha256,
)

if plan["can_apply"]:
    reimport_ifc_semantics_to_project(
        project,
        revised_semantics,
        source_name="facility-v2.ifc",
        source_sha256=revised_source_sha256,
    )
```

Re-import compares each bound IFC object against the source-derived spatial
baseline from the prior import:

- source-only changes are applied while preserving the existing CleanroomX ID;
- local-only spatial edits are preserved when the IFC object is unchanged;
- source additions and unchanged source deletions are applied;
- matching two-sided edits are treated as converged;
- different local and source edits to the same bound object are explicit
  conflicts;
- unbound local rooms/devices are preserved;
- the merged candidate must pass canonical spatial validation before mutation.

Conflict detection is fail-closed and transactional: a conflicting or invalid
candidate leaves both `spatial_layout` and `ifc_link` unchanged. Projects that
contain the older schema-v1 IFC link remain readable, but must perform one fresh
IFC import before conflict-aware re-import because v1 did not retain element-level
GlobalId bindings.

The semantic normalization API is also public. Integrations can provide already
extracted IFC records without installing IfcOpenShell:

```python
from cleanroomx.bim_ifc import (
    layout_from_ifc_semantics,
    normalize_ifc_semantic_records,
)

semantics = normalize_ifc_semantic_records(records)
layout = layout_from_ifc_semantics(semantics)
```

## Intentional limitations

This is a semantic and quantity-based interoperability layer, not a full IFC
geometric kernel.

The current CleanroomX spatial contract is axis-aligned. The bridge therefore
uses room Length / Width / Height quantities and placement origins. Parent
translations are resolved, but arbitrary parent rotation, B-Rep tessellation,
complex solids, curved boundaries, multi-storey decomposition, door/window
void geometry, and automatic engineering-analysis reconciliation are not yet
claimed.

Those limitations are explicit so imported data cannot silently imply geometric
precision that the current model does not preserve.

## Next extension path

The bridge establishes stable IFC identity and provenance needed for later work:

1. geometry/tessellation and rotated-coordinate support;
2. explicit IFC storey/floor mapping;
3. IFC property-set mapping to cleanroom classifications and engineering inputs;
4. richer property-set review and explicit engineering synchronization proposals;
5. bidirectional synchronization and digital-twin/CFD integration.

No IFC-derived engineering value is currently written directly into a solver
input without an explicit future synchronization step.
