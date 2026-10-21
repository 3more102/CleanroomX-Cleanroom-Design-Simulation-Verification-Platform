# Actual CleanroomX GUI captures — 21 October 2026

These 17 images are actual Tk window pixels or native VTK framebuffer captures. The numerical views use the archived, genuinely executed Foundation v10 case at SIMPLE iteration **100**, which is **not solver-converged**. Engineering release remains **HOLD**. Design pressure overlays and arrows describe input intent. Particle counts are representative numerical samples, not airborne concentration.

| Image | Actual displayed content |
|---|---|
| [01-main-workspace.png](01-main-workspace.png) | Running CleanroomX start workspace with the bundled input project |
| [02-design-studio.png](02-design-studio.png) | Actual 3D design geometry; design arrows/pressure intent are not CFD fields |
| [03-multiroom-design.png](03-multiroom-design.png) | Synchronized actual 2D/3D multiroom input geometry |
| [04-object-inspector.png](04-object-inspector.png) | Actual selected-room property inspector |
| [05-simulation-workspace.png](05-simulation-workspace.png) | Real imported OpenFOAM room/door p and phi review; nonconvergence/HOLD retained |
| [06-original-openfoam-mesh.png](06-original-openfoam-mesh.png) | Original verified polyMesh cell edges on the selected recorded z layer |
| [07-computed-velocity-section.png](07-computed-velocity-section.png) | Actual recorded cell velocity magnitudes/vectors on a z layer; no interpolated cells |
| [08-pressure-and-airflow.png](08-pressure-and-airflow.png) | Computed room pressures, door deltas and face-flux airflow balances |
| [09-particle-injection.png](09-particle-injection.png) | Actual source editor with two saved fluid sources, diameter/density/count and release schedules |
| [10-computed-particle-tracking.png](10-computed-particle-tracking.png) | Actual integrated particle paths and release-aware recorded-sample markers in computed 3D U |
| [11-residual-graphs.png](11-residual-graphs.png) | Actual saved solver initial/final residual histories |
| [12-iteration-analysis.png](12-iteration-analysis.png) | Actual saved SIMPLE pressure/continuity observations; iteration is not physical time |
| [13-particle-population.png](13-particle-population.png) | Computed numerical particle population chart/table from eight scheduled frozen-U trajectories |
| [14-3d-review-controls.png](14-3d-review-controls.png) | Actual 3D field/source/mesh and particle playback controls |
| [15-computed-3d-velocity.png](15-computed-3d-velocity.png) | Actual recorded 3D velocity samples with isometric camera; no interpolated volume field |
| [16-computed-3d-pressure.png](16-computed-3d-pressure.png) | Actual recorded 3D relative pressure samples in Pa, using explicit density/reference |
| [17-particle-source-closeup.png](17-particle-source-closeup.png) | Actual camera close-up of computed process-source paths; no trajectory scaling or synthetic motion |

Per-image hashes and source identity: [capture manifest](../../reports/engineering-session-20261021/capture-manifest.json). Reproduce with [the capture script](../../scripts/capture_recorded_cfd_gui.py), an actual display and an existing verified solver case.
