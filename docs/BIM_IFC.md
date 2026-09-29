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
4. GUI import/review workflow;
5. bidirectional synchronization and digital-twin/CFD integration.

No IFC-derived engineering value is currently written directly into a solver
input without an explicit future synchronization step.
