# CAD-to-CFD suite topology preflight

CleanroomX's existing project-native **Design 2D + 3D** workspace stores rooms,
devices, and elevations in `project.metadata.spatial_layout`. The existing
OpenFOAM Foundation v10 exporter is an **empty single rectangular room** workflow,
not a multi-room CAD compiler. This feature is a read-only, fail-closed
**topology preflight**, not a CFD mesher or solver.

## GUI

Open a project with a spatial layout. In **Design 2D + 3D**, click
**CFD topology preflight** on the Engineering Overlay toolbar. The dialog reports:

- Positive-area shared partitions from actual X/Y/Z room coordinates
- Door/opening/transfer records mapped wholly into their shared partitions
- Overlaps, gaps, disconnected rooms, invalid/unassigned/oversized openings
- Duplicate/overlapping openings and stepped floor or ceiling elevations

The GUI does not run a solver or modify the project. For more than 12 issues,
export the complete machine-readable preflight report through the CLI.

## Commands

On Windows PowerShell from the repository root:

```powershell
$env:PYTHONPATH = "$PWD\src"
py -3 -m cleanroomx.cfd_pipeline_cli suite-preflight `
    examples/cfd_suite_topology_demo.cleanroomx.json `
    --output "$env:TEMP\cleanroomx-suite-preflight.json"
```

On Linux / WSL after `pip install -e .`:

```bash
cleanroomx-cfd-pipeline suite-preflight \
    examples/cfd_suite_topology_demo.cleanroomx.json --output /tmp/suite-preflight.json
```

Exit code **0** means *geometry topology valid only*; **3** means topology
blocked; **1** may mean output publication failed. None means CFD validated.
The report always says `ready_for_solver: false` and
`openfoam_case_status: not_generated`.

The new `cfd_suite_topology_demo.cleanroomx.json` is a clearly marked
**concept-only** three-room facility with aligned shared walls, two connecting
doors, and a legitimate exterior entry. It provides a positive geometry-topology
example for the 2D/3D viewer and CLI, not CFD or ISO qualification.

The older `gui_demo.cleanroomx.json` intentionally contains 1 m gaps between
rooms; the preflight reports that older layout as disconnected rather than
inventing internal passages.

## Engineering boundaries

- Canonical layout schema validation precedes checks; invalid geometry is never normalized into a pass.
- Positive X/Y/Z volume overlap blocks geometry preflight. A corner touch does not define a wall.
- A connecting opening requires an assigned room, wall_side, width, height and compatible shared-wall location and elevation.
- Non-coincident floors and ceilings at a shared partition trigger an explicit stepped-wall warning/blocker.
- The geometry report includes a SHA-256 digest of the supplied spatial layout.
- No pressure cascade or ISO compliance is inferred from coordinates or color-coded rooms.
- Spatial HVAC device positions do not supply duct airflow, terminal patch dimensions, filter resistance, turbulence or mass-flow boundary conditions.
- The current model does not persist door-undercut gap dimensions; the preflight never invents a 12 mm gap or a 3 m/s minimum.
- Actual multi-room OpenFOAM meshing requires watertight fluid topology, explicit partition thickness, openings, valid boundary patches,
  solver residuals, mass fluxes, grid-independence evidence, and model-specific physical validation.

This does **not** yet implement multi-room hex meshing, SST k-omega, virtual smoke
wand animation, interactive VTK streamline visualization, regulatory certification,
or a Qt desktop migration. Existing CFD exporter, 3D workspace, and rule packs
remain available without modification.

## Regression

```bash
python -m pytest -q tests/test_cfd_suite_topology.py
# With a GUI display:
python -m pytest -q tests/test_spatial_editing_gui.py
```

Regression geometry is synthetic; passing tests cannot qualify a real cleanroom.
