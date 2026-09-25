# CleanroomX 2D / 3D Spatial Design

CleanroomX stores spatial design data inside the normal `cleanroomx.project` document under
`project.metadata.spatial_layout`. The 2D editor and 3D viewer use the same canonical model;
there is no separate 3D geometry copy.

## Spatial model

A layout records one floor definition, grid spacing, rooms, placed devices/openings, and viewport
settings. Existing projects that do not contain spatial metadata still open normally. Existing
version-1 layouts that predate floor metadata are defaulted to a metric `Floor 1` at elevation
0 m with a 3 m default ceiling.

Floor data includes a stable ID, floor name, elevation, default ceiling height, and metric units.
Rooms have stable IDs, X/Y position, length, width, height, floor elevation, optional pressure
with explicit provenance (`user` or `engineering_input` when known), optional project-defined
classification text, and an optional `analysis_room_name` link.
Devices use stable IDs and support doors, supply diffusers, return grilles, exhaust grilles,
FFUs, equipment, sensors, and transfer openings. Door/transfer records may carry width, height,
wall side, orientation, and swing metadata.

## 2D editor

Open **Design 2D + 3D** in the desktop application. The 2D side supports:

- room creation, selection, drag movement, corner-handle resizing, deletion, and property editing;
- placed doors, supply, return, exhaust, FFU, equipment, sensor, and transfer objects;
- configurable metric grid spacing through **Floor…** and independently switchable snap-to-grid;
- zoom, pan, fit-to-view, coordinate feedback, selection highlighting, and project-wide undo/redo;
- optional labels, device visibility, pressure overlay, and pressure-cascade relationship arrows;
- floor area, room volume, room count, and key device-count summaries.

Dragging a room also translates devices assigned to that room. The blue lower-right handle of a
selected room resizes its footprint. The property inspector can edit device Z elevation, room
association, opening dimensions/orientation/wall side/swing, room floor elevation,
classification text, and analysis-room linkage.

Pressure color is shown only when a room has a supplied pressure value. Room labels distinguish
user-entered pressure from pressure copied from an engineering input when that provenance is known.
Relationship arrows are drawn only from the active analysis's explicit `pressure_cascade` records.
When both linked rooms have supplied pressures, each relationship reports the observed pressure
delta and marks the configured minimum relationship as pass or fail; missing pressure remains
explicitly unavailable. CleanroomX does not invent missing pressure, airflow values, or a
calculated pressure field.

## 3D viewer

The right side projects the same room footprints and heights into an interactive pure-Tk 3D
view. It renders the floor plane, room top/wall geometry, room labels, and placed devices/openings.
Mouse wheel zooms. Middle/right drag pans. The rotate, tilt, reset, and fit controls move the
camera. Fit-to-view uses deterministic tested projection math over every room corner, including
floor elevation and ceiling height, and recenters both 3D pan axes. Selecting a room or object in
3D selects the same canonical object used by the 2D editor.

Room floor elevation and room height control the vertical extrusion. Device Z is relative to its
assigned room floor elevation. Door and transfer-opening height is rendered from the same device
record used in 2D.

## Engineering synchronization

Spatial editing does not silently alter engineering inputs. Use **Sync dimensions to active
analysis** explicitly. For room-verification and project-verification workflows, CleanroomX can
copy the spatial room length, width, height, and an already-supported observed pressure field.
Other engineering inputs are preserved.

A room can keep a stable `analysis_room_name` even when its display name changes. Duplicate
links and links to a missing analysis room are rejected instead of being applied ambiguously.
The workspace reports room-level synchronization state as **synchronized**, **geometry newer**,
**engineering newer**, **conflicting**, or **unmapped**. "Newer" is reported only when a persisted
last-synchronized geometry baseline proves which side changed. If geometry differs without that
provenance, CleanroomX reports **conflicting** rather than guessing. The baseline stores only the
common room dimensions and mapping identity; it does not duplicate solver outputs.

Synchronization resolves and validates every room mapping before changing any engineering input,
so a later bad link cannot leave a partially updated analysis. After an actual engineering-input
change, the affected analysis must be validated/run again; prior results are not treated as current.

## Persistence and validation

Spatial data uses the existing project persistence path, including strict JSON parsing, atomic
writes, guarded overwrite behavior, autosave/recovery, saved revisions, and project undo/redo.
The persistence boundary rejects non-finite geometry, non-positive dimensions, duplicate IDs,
dangling room references, unsupported device types, malformed view flags, and unsupported future
layout versions.

Interactive spatial checks additionally report overlapping room footprints, duplicate room names,
unassigned/orphan devices, devices outside their assigned room, and invalid device elevations.
These checks are geometry/model-integrity checks, not cleanroom certification criteria.

## Demo

`cleanroomx-gui --demo` opens the verification analysis with an explicit three-room spatial
layout for Process, Preparation, and Ante/Airlock, together with engineering-input pressure
provenance, pressure-cascade relationships, doors, supply/return devices, an FFU, equipment,
and a transfer opening.

For an automated GUI smoke path on Linux with a virtual display:

```bash
xvfb-run -a cleanroomx-gui --demo --smoke
```

The smoke command fails closed unless the packaged demo loads, the active analysis runs, the real
2D room geometry renders, the 3D room geometry renders, and pressure-cascade relationship graphics
are present.

## Engineering boundary

The 2D/3D workspace is a deterministic design and visualization layer over CleanroomX project
data. It is not CFD, airflow-field simulation, ISO cleanroom classification, commissioning/TAB
acceptance, regulatory approval, or manufacturer approval. Real design and qualification still
require the applicable licensed standards, project requirements, calibrated measurements, and
qualified engineering judgment.
