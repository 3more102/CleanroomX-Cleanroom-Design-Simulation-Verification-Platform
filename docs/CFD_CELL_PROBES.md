# Recorded CFD cell probes

Import a completed case through the existing **Import computed fields** action,
then open **Computed sections**. The canonical importer still checks the case
inputs, execution receipt, original logs, mesh and field hashes.

1. Choose **Probe cell**, then click a coloured fluid cell in an x/y/z section.
   A cyan outline and cross mark the selected cell. **Streamline** remains the
   default click mode and retains its existing tracing behaviour.
2. Alternatively, enter **X/Y/Z (m)** and select **Probe XYZ**. Coordinates use
   the entire imported field. The section shows a marker only when the selected
   cell is on the current plane and passes the room filter.
3. Inspect the table and full-precision readout: zero-based OpenFOAM cell index,
   room, selected SIMPLE iteration, cell centre, Ux/Uy/Uz, speed and pressure in
   Pa relative to the imported reference room. The air density and recorded
   convergence flag remain visible in the readout. Selecting an earlier table
   row redraws that cell's marker.
4. **Export probes** creates a new JSON file with up to 100 selections, retaining
   both the requested XYZ and the source cell centre. It includes the manifest
   and run-receipt SHA-256 identities, iteration, density and pressure reference.
   Export recomputes each selection against the current imported field and
   rejects changed/stale values or a different density/reference. It never
   overwrites an existing file.

**Clear probes** clears the measurement list and marker. Reimporting fields,
starting a new case/run or browsing to another case resets all probe data and
the cached spatial index. Selection and export are blocked during execution.
The section panel scrolls in both directions at smaller window sizes.

## Sampling definition

The regular occupied-voxel index reads the containing cell's recorded value.
There is no interpolation or nearest-fluid-cell fallback. Missing voxels,
walls, an excluded room and positions outside the field return no reading.
Voxels use `[centre - pitch/2, centre + pitch/2)` on each axis: the cell on the
positive-coordinate side owns a shared face. A voxel's unoccupied upper face
does not inherit the preceding cell's reading.
Lookup evaluates the recorded decimal coordinate/pitch representations, so
binary division cannot move an exact 0.1 m grid face into the preceding cell.
Nearby points are not snapped to faces.

The pressure is already converted from kinematic pressure using the imported
air density and reporting room mean. Probes do not convert it again. Speed is
the magnitude of the recorded three-component velocity vector. The requested
point and cell-centre sample location remain distinct in exported data.

These are recorded cell-centred CFD values, not pointwise spatial accuracy or
physical measurements. SIMPLE iteration labels are not physical seconds.
Inspecting a field does not establish numerical convergence, grid independence,
closed-door 5 Pa performance or cleanroom acceptance. **Engineering release
remains HOLD.**

## Verification

```bash
python -m pytest -q tests/test_cfd_cell_probes.py tests/test_cfd_cell_probes_archive.py
xvfb-run -a python -m pytest -q tests/test_cfd_cell_probes_gui.py
bash scripts/with_openfoam10.sh xvfb-run -a python -m pytest -q \
  tests/test_cfd_multizone_execution.py -ra
```

The archive suite replays the original hash-checked 13,210-cell case and checks
all cell indices and p/U readings at saved iterations 25, 50, 75 and 100 against
the original arrays. This is archived-field verification, not a new solver run.
The actual-execution suite separately runs Foundation v10 and checks the native
probe UI against its new outputs. The display workflow exercises real Tk on
Linux; the Windows CI job also runs the probe UI and archived-field checks.
