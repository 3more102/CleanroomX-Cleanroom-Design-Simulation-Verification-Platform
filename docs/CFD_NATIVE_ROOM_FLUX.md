# Native doorway flow and room balances

The **Two-room doorway transfer and balances** graph uses native OpenFOAM
Foundation v10 `surfaceScalarField phi`, not interpolated cell velocity.
It is available for newly executed generated two-room cases whose receipts
contain the `room_flux` extension. The `two-room-analyze` CLI exports the same
graph, source hashes, CSV data and ProofGraph.

## Computation and evidence

- Read `points`, `faces`, `owner`, `neighbour`, `boundary` and the exact final
  solver-time `phi` file. Bind all six artifacts, plus the case manifest, to
  their SHA-256 hashes. New run receipts include the four additional topology
  files in `result_sha256`; existing boundary/phi bindings remain required.
- Reconstruct native closed, oriented hexahedral cell shells independently
  of VTK ordering. Check rectangular geometry, room bounds, complete unique
  cell tiling, cell counts/resolution and both room volumes against the
  regenerated case manifest. The supported scope is the serial, static,
  axis-aligned two-room fixture; arbitrary meshes are rejected.
- Select only internal faces connecting different rooms at the declared
  doorway. Check face orientation, opening bounds and summed doorway area.
  Inspect external patch locations and allocate them by their native owner.
- Positive `phi` leaves an internal face's owner and enters its neighbour.
  Reorient each doorway value so positive means **Room 1 → Room 2**. Report
  gross flow in each direction and their signed net. Per-room balances sum
  external outward flow and signed doorway outward flow; same-room internal
  contributions cancel. No balance acceptance threshold is invented.
- Recompute the full diagnostic during ProofGraph ingestion and compare it
  with the receipt. Recheck all sources after computation and before export.
  The graph honors exact decimal solver-time and case selections.

The sign convention follows the Foundation v10 implementation:
[fvcSurfaceIntegrate.C](https://cpp.openfoam.org/v10/fvcSurfaceIntegrate_8C_source.html)
adds an internal surface value to the owner and subtracts it from the neighbour.
[createPhi.H](https://cpp.openfoam.org/v10/src_2finiteVolume_2cfdTools_2incompressible_2createPhi_8H_source.html)
defines the incompressible face-flux field.

Older v2 receipts without topology binding keep existing pressure and global
flow diagnostics. Doorway flow remains **unavailable** for those receipts;
the application never silently upgrades them by reading unbound mesh files.
An explicitly offline archive replay can inspect those bytes separately,
with its narrower provenance scope recorded.

## Recorded offline replay

The archive from [Foundation v10 workflow run 39159459313](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/39159459313)
was downloaded and its published ZIP SHA-256 verified. Replaying the new
native diagnostic against the untouched two-room mesh and `150/phi` produced:

| Quantity | Diagnostic value |
| --- | ---: |
| Solver iteration | 150 |
| Doorway internal faces / area | 2 / 0.044 m² |
| Room 1 → Room 2 gross and net flow | 0.10020442339 m³/s |
| Room 2 → Room 1 gross flow | 0 m³/s |
| Room 1 / Room 2 cells | 1,152 / 1,152 |
| Room 1 / Room 2 volume | 72 / 72 m³ |
| Room 1 net outward balance | +0.0002044233896 m³/s |
| Room 2 net outward balance | −0.00137933206681 m³/s |

Full source hashes and replay scope are in
[cfd-doorway-flux-replay-2026-10-18.json](evidence/cfd-doorway-flux-replay-2026-10-18.json).
The archive's original v2 receipt does **not** contain the new topology
extension; it was not modified or presented as a new solver execution.
Its full archive digest supplies the replay provenance. This offline replay
does not exercise the new execution-receipt writer.

## Validation scope

Synthetic native meshes test bidirectional flow, reversed owner numbering,
source mutation, invalid addressing, geometry, dimensions and time labels,
self-rehashed forged receipts, graph filtering and source-checked exports.
Real Tk tests exercise the new graph through the asynchronous explorer.
Actual widget captures at 1180×820 and 1050×680, visibly labelled as synthetic
fixtures, are in `docs/screenshots/cfd-doorway-flow/`; reproduce them on a
display with `python scripts/capture_cfd_doorway_explorer.py`.
The Foundation v10 smoke script now requires the new receipt extension,
replays it through ProofGraph, and exports both field and doorway graphs.

The reported imbalances remain visible. This feature does not assess coupled
solver convergence or mesh independence. Transfer flow alone does not identify
outdoor/fresh-air supply, air age or ventilation effectiveness; **per-room ACH
remains NOT_ASSESSED**. Physical cleanroom validation remains **BLOCKED**.

## Completed local verification

- Full Python 3.12 repository regression on a real virtual display:
  **2,836 passed, 1 skipped**, 166.85 seconds. The skip is the optional native
  IFC/BIM dependency. Command: `python -m pytest -q -ra -o faulthandler_timeout=40`.
- The suite includes 32 new native-flow/receipt/export checks and the actual
  Tk doorway graph test. GUI captures were visually inspected at both sizes.
- Workflow YAML parsing, Python compilation, screenshot/source hash checks
  and `git diff --check` passed. The archived native replay above passed
  against its original verified receipt and published archive digest.
- No OpenFOAM solver was started locally. Fresh execution of the new receipt
  writer and smoke/export gate is delegated to the Foundation v10 CI workflow;
  its outcome must be read separately from the completed local regression.
