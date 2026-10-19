# Foundation v10 execution, synchronization, and visualization evidence

**Status:** Real OpenFOAM execution and output-ingestion diagnostics passed;
scientific validation remains **BLOCKED**.

## Exact-head run

- Repository branch: `codex/openfoam-v10-boundary-input-audit-20261015`
- Code head: `a814c1bc80576ea62ec5c842b056a8546701cf9f`
- OpenFOAM workflow: [run 38894717248](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38894717248)
- Runtime: OpenFOAM Foundation v10, build `10-c4cf895ad8fa`
- Artifact: [12043676936](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38894717248/artifacts/12043676936), 32,589,567 bytes; GitHub reports SHA-256 `3a297e0c88ae643f02a3b197820c89d5b14b979408cea8176b5883bac49d8cb6`.
- Exact-head CI: [run 38894717251](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38894717251) passed Python 3.11, 3.12, and 3.13 jobs plus the wheel, Windows launcher, and native BIM smoke jobs. [VTK regression 38894717264](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38894717264) passed.

The workflow artifact contains generated cases, native OpenFOAM fields and logs,
VTK exports, synchronization manifests and snapshots, parity summaries, and
the airflow plot. The evidence describes synthetic cases and is not a
cleanroom qualification report.

## Solver execution and mesh data integrity

The workflow generated three synthetic room configurations at coarse, medium,
and fine levels, with 216, 1,728, and 13,824 cells per level and a 12 m³ room
volume. For all nine cases, `blockMesh`, `checkMesh`, and `simpleFoam` returned
zero. Generated boundary faces, normals, and prescribed inlet flows passed the
boundary audit. OpenFOAM `checkMesh` volume totals matched the `polyMesh` cell
volume sum and the synthetic room bound for all nine meshes.

These results establish successful execution and mesh-data consistency for
this synthetic family. The resolution levels alone do not establish mesh
convergence or mesh independence.

## Native-to-VTK parity and incremental synchronization

The final-time export audit compared native OpenFOAM `U`, kinematic pressure
`p`, and surface flux `phi` with the VTK representation for each case. All nine
internal-field checks and the boundary patch and surface-flux checks passed
within the measured float32 and ASCII serialization bounds. These bounds test
data transfer fidelity; they are not solver acceptance tolerances.

A separate `foamToVTK` run selected times 50 and 100 for all nine cases. The
workflow verified 283,824 velocity components, 94,608 pressure values, 27,216
patch faces, and 297,432 surface-flux faces across those exports. The
incremental VTK synchronizer accepted three snapshots at times 50, 100, and
150 for each of the nine cases: 27 snapshots total. The records include source
and snapshot hashes, simulation and configuration identifiers, mesh cell
counts, and solver times. Turbulence fields were reported unavailable in
these laminar cases; no temperature or contaminant field was produced.

## Residual and flow-balance screens

All nine cases produced 150 logged time steps. The terminal residual screen
remained `NOT_BELOW_TOLERANCE` for velocity `U` and pressure `p` in every case.
The measured inlet/outlet flux-imbalance range was 0.005341% to 0.187145%.
The report labels these measurements diagnostic only because the project has
not defined a justified flow-balance acceptance criterion. A zero solver exit
code and successful VTK parity do not establish numerical or physical
convergence.

## Visualization

The workflow generated an airflow speed plot from the synchronized final-time
coarse-grid snapshots:

- Cross-section: `y = 1.0 m`, slab thickness `0.5 m`
- Samples: 72 cell centers per configuration
- Sampled speed range: 0.003429–0.222541 m/s
- Report status: `sampled_cells_visualized_not_cfd_validation`

The artifact contains `cleanroomx-openfoam-visualization/airflow-speed-cross-section.png`
and its JSON sampling report. The plot displays cell-center samples; it is not
an interpolated contour or a physical-validation result.

## Scientific limits and next evidence

The cases use idealized rectangular geometry and simplified, steady,
incompressible laminar boundary conditions. They do not model qualified
cleanroom geometry, filter or diffuser performance, turbulence, buoyancy,
particle/contaminant transport, or site-specific operation. No project
acceptance thresholds, analytical benchmark comparison, independent measured
cleanroom comparison, uncertainty analysis, or eligible three-grid
convergence result is established here. This run does not support ISO 14644
classification or qualification claims.

Completing validation requires matched facility geometry and operating
conditions, measured supply/extract flow and room pressure data with
uncertainty, applicable particle or contaminant measurements, physical-model
inputs, and project-defined tolerances justified for the intended use.
