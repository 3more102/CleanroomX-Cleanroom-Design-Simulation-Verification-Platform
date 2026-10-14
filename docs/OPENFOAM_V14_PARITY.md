# OpenFOAM Foundation v14 capability parity

## Baseline and scoring rule

The target is **OpenFOAM Foundation v14**, release tag [`version-14`](https://github.com/OpenFOAM/OpenFOAM-14/tree/version-14), peeled source commit `b4f91ad8bbbab628441562fc419f040cc4796f11`. The Foundation announced v14 on 14 July 2026. This is the Foundation distribution, not the separately maintained OpenCFD/OpenFOAM.com distribution. The target is pinned to the release tag so future patch tags do not silently change the denominator.

The official v14 [User Guide PDF](https://github.com/OpenFOAM/OpenFOAM-14/blob/version-14/doc/Guides/OpenFOAMUserGuide-A4.pdf), official [release notes](https://openfoam.org/release/14/), and the tagged source tree are the comparison references. The row-level trace is in [`OPENFOAM_V14_CAPABILITY_MATRIX.csv`](OPENFOAM_V14_CAPABILITY_MATRIX.csv).

Each score counts only rows whose status is `complete`; the matrix validator requires an implementation path and an explicit `PASS:` evidence reference. Synthetic, mocked, fixture, simulated, and generated-only evidence cannot complete integration or workflow rows. `partial`, `unsupported`, `not_tested`, and `blocked` rows count as incomplete. Generated case files and CI results do not count as OpenFOAM solver runs or scientific validation.

The catalogue covers every numbered v14 User Guide entry; all solver and utility executable targets in application `Make/files`; every executable script under `bin` and `etc`; every top-level `applications/modules` package and `src` library package; every literal `add*ToRunTimeSelectionTable(...)` registration found under `src` and `applications`; and every tutorial `Allrun` script. The guide introduction is retained as a reference row but is outside all score denominators. Issue #1296's cleanroom workflow denominator consists of nine real runs, three per-layout grid audits, and four provenance/physics/measurement/evidence gates.

OpenFOAM Foundation v10 is tracked separately in the [v10 matrix](OPENFOAM_FOUNDATION_V10_PARITY.md), pinned to its own source commit and User Guide. Its denominators are not combined with the v14 scores below.

Regenerate and source-check the matrix from a local checkout of the exact release tag (with Poppler `pdftotext` installed):

```bash
python -m cleanroomx.openfoam_parity \
  docs/OPENFOAM_V14_CAPABILITY_MATRIX.csv \
  --generate-openfoam-source /path/to/OpenFOAM-14 \
  --verify-source /path/to/OpenFOAM-14
```

Score the checked-in matrix without a solver installation:

```bash
python -m cleanroomx.openfoam_parity docs/OPENFOAM_V14_CAPABILITY_MATRIX.csv
```

## Current scores

These are exact row counts from the checked-in matrix on 14 October 2026. They do **not** claim parity: none of the required rows has end-to-end v14 evidence, and none of the cleanroom validation gates has been closed.

| Measure | Complete | In-scope rows | Score |
|---|---:|---:|---:|
| Native solver capability parity | 0 | 1,595 | 0.00% |
| End-to-end OpenFOAM integration | 0 | 2,130 | 0.00% |
| Validated cleanroom engineering workflows | 0 | 16 | 0.00% |

### Category scores

| Category | Native | Integration | Cleanroom workflow |
|---|---:|---:|---:|
| applications_and_apis | 0/31 | 0/45 | — |
| case_management_tools | — | 0/35 | — |
| case_setup_and_numerics | 0/55 | 0/56 | — |
| case_template_workflows | — | 0/14 | — |
| deprecated_utilities | — | 0/2 | — |
| developer_tools | — | 0/12 | — |
| evidence_integration | — | — | 0/1 |
| fields_and_boundary_conditions | 0/22 | 0/23 | — |
| grid_convergence | — | — | 0/3 |
| measured_validation | — | — | 0/1 |
| mesh | 0/51 | 0/52 | — |
| mesh_utilities | — | 0/59 | — |
| miscellaneous_utilities | — | 0/6 | — |
| parallel_utilities | — | 0/3 | — |
| physical_models | 0/26 | 0/27 | — |
| physics_model_review | — | — | 0/1 |
| postprocessing | — | 0/41 | — |
| postprocessing_utilities | — | 0/15 | — |
| preprocessing_utilities | — | 0/15 | — |
| public_api_libraries | 0/43 | 0/43 | — |
| real_solver_runs | — | — | 0/9 |
| run_provenance | — | — | 0/1 |
| runtime_boundary_conditions | 0/4 | 0/4 | — |
| runtime_function_objects | 0/134 | 0/134 | — |
| runtime_mesh | 0/220 | 0/220 | — |
| runtime_numerics | 0/2 | 0/2 | — |
| runtime_physical_models | 0/428 | 0/428 | — |
| runtime_selection_other | 0/465 | 0/465 | — |
| runtime_sources_constraints | 0/85 | 0/85 | — |
| solver_applications | 0/5 | 0/5 | — |
| solver_entrypoint_scripts | — | 0/30 | — |
| solver_modules_base | 0/5 | 0/5 | — |
| solver_modules_combustion | 0/1 | 0/1 | — |
| solver_modules_compressible | 0/2 | 0/2 | — |
| solver_modules_film | 0/2 | 0/2 | — |
| solver_modules_multiphase | 0/9 | 0/9 | — |
| solver_modules_particles | 0/1 | 0/1 | — |
| solver_modules_single_phase | 0/2 | 0/2 | — |
| solver_modules_solid | 0/2 | 0/2 | — |
| surface_utilities | — | 0/29 | — |
| thermophysical_utilities | — | 0/5 | — |
| tutorial_documentation | — | 0/43 | — |
| tutorial_workflows | — | 0/208 | — |

## Implemented evidence and limits

- CleanroomX can generate v10 cases by default and now has a separate v14 case path. The v14 path writes `solver incompressibleFluid`, v14 `physicalProperties` and `momentumTransport` dictionaries, and selects `foamRun` for external execution.
- The existing nine-case grid-generation and issue #1296 validation path remain OpenFOAM Foundation v10. This version split is explicit; v10 evidence is not v14 evidence.
- Local checks exercise generated dictionary contents and mock the external commands. OpenFOAM is not installed in the current environment. There is no real v14 run in this change. The runner now requires matching Foundation shell variables and an executable version banner, and records command, environment, input-hash, return-code and log-hash provenance in a local `run_manifest.json`; this is not an immutable external archive.
- CleanroomX still has no native finite-volume CFD solver. It does not implement OpenFOAM's broad scheme, boundary-condition, linear-solver, model, utility, API, parallel, and tutorial catalog.
- The cleanroom workflow score is 0/16. No real nine-case v10 run bundle, three real grid audits, independent model review, measured-data correlation, or ProofGraph evidence package is available. Issue [#1296](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/issues/1296) remains open.

The largest next integration gap is reproducible real execution under the pinned v14 installation, including generated v14 cases, `checkMesh`, `foamRun`, solver-log handling, and VTK export/import. Closing that gap would not increase native solver parity or satisfy the independent cleanroom-validation gates.

## Verification record

Recorded 14 October 2026 on Python 3.12.14, pytest 9.1.1, and Poppler `pdftotext` 24.02.0. The comparison checkout is OpenFOAM Foundation `version-14`, commit `b4f91ad8bbbab628441562fc419f040cc4796f11`.

| Command | Result | Evidence limit |
|---|---|---|
| `.venv/bin/cleanroomx-openfoam-parity docs/OPENFOAM_V14_CAPABILITY_MATRIX.csv --generate-openfoam-source ../openfoam14 --verify-source ../openfoam14 --format markdown` | Passed; 2,147 row IDs matched the pinned source and guide inventory. | Static inventory/score check only. |
| `.venv/bin/python -m pytest tests/test_cfd_pipeline.py tests/test_openfoam_parity.py tests/test_openfoam_v10_capability_matrix.py tests/test_cfd_grid_study.py -q` | 60 passed in 4.73 s. | Adapter commands are mocked; grid data are synthetic. |
| `.venv/bin/python -c 'import vtk, matplotlib; print(vtk.vtkVersion.GetVTKVersion(), matplotlib.__version__)' && .venv/bin/python scripts/openfoam_v10_parity_score.py && .venv/bin/python -m pytest -q tests/test_cfd_study.py tests/test_cfd_pipeline.py tests/test_cfd_scalar_audit.py tests/test_cfd_grid_study.py tests/test_cfd_convergence_triage.py tests/test_openfoam_v10_capability_matrix.py -ra` | VTK 9.7.1 and Matplotlib 3.11.2 available; v10 matrix scorer passed at 0/192, 0/717, 0/21; 157 tests passed in 6.20 s. | CFD and matrix software regressions only. |
| `.venv/bin/python -m pytest -q` | No completed result on this rebased head; the local run was interrupted at about 35%. | Exact-head GitHub CI is the broad regression gate. |

Before the rebase incorporated the two Foundation v10 matrix commits, a full local suite completed with 2,374 passed and 81 skipped in 416.89 s. That older result is not counted as exact-head evidence for this combined branch.

`foamVersion`, `foamRun`, `blockMesh`, `checkMesh`, and `simpleFoam` were unavailable in this environment, and no container runtime was available. There was no OpenFOAM execution, no solver convergence review, no mesh-independence result, and no independent cleanroom measurement. All scientific-validation gates remain blocked.
