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
  semantic SHA-256, and imported room/device counts

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
4. conflict-aware re-import using persisted IFC `GlobalId` identity;
5. GUI import/review workflow;
6. bidirectional synchronization and digital-twin/CFD integration.

No IFC-derived engineering value is currently written directly into a solver
input without an explicit future synchronization step.
