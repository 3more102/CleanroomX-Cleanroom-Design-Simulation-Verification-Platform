# OpenFOAM Foundation v10 capability parity

## Target and source boundary

The comparison target is **OpenFOAM Foundation v10**, from the OpenFOAM
Foundation distribution. It is not OpenCFD/ESI OpenFOAM v2306/v2606 or a
Foundation v11+ release. The standard solver and utility catalogs use the
Foundation v10 user guide. Source paths and tutorials are pinned to
[`OpenFOAM-10` commit `89f925dc708d068f84f51e8317e3bebcda64f5cb`](https://github.com/OpenFOAM/OpenFOAM-10/tree/89f925dc708d068f84f51e8317e3bebcda64f5cb).

The [capability matrix](openfoam_foundation_v10_capabilities.csv) traces each
row to an upstream guide section or pinned source path and records separate
native, integration, and cleanroom statuses, implementation path, test
evidence, and remaining gap. The [source inventory](openfoam_foundation_v10_source_inventory.csv)
records 72 solver-tree `Make/files` units, 151 utility-tree units, 94 `src`
library/API build units, and all 240 tutorial cases containing a
`system/controlDict`. Together with the guide catalogs, the matrix includes
49 documented solver applications, 149 utility entries (140 from the guide
catalog and 9 additional source-tree tools), 23 solver-tree model/source
components, and the project-specific workflow gates.

The turbulence rows enumerate the Foundation v10 user guide's 19
incompressible RAS models, 14 compressible RAS models, and 10 LES models for
each compressibility family.

The matrix has individual rows for the guide-listed geometric patch types,
basic boundary conditions, selected derived conditions and wall functions;
seven `fvSchemes` term categories; six named time-scheme choices; and six
linear-solver algorithms. The v10 guide says its boundary-condition lists are
not complete and describes many additional scheme variants. The API inventory
is at the source build-unit level: it does not enumerate every C++ class,
runtime registration, boundary-condition/plugin type, scheme variant,
dictionary keyword, or third-party dependency as its own row. This explicit
boundary prevents a high aggregate score from being mistaken for
symbol-by-symbol API parity; a full runtime-registry inventory remains work.

## Status and scoring rules

For each track, the score is `complete rows / rows with status other than na`.
`complete` requires an implementation path, `test_evidence` beginning with
`PASS:`, and `remaining_gap` set to `none`. A complete integration row must use this exact
structured evidence form: `PASS: OpenFOAM Foundation v10; non-synthetic run; run_manifest=<HTTPS URL>; manifest_sha256=<64 hex characters>`. This prevents a negated prose sentence from qualifying because it contains matching
substrings. Complete cleanroom rows still require measured evidence and
uncertainty. `partial`, `blocked`, and `unsupported` remain in the denominator and do not count in the numerator.
`na` means the row does not belong to that track and is excluded. The scoring
script rejects missing fields, invalid states, duplicate IDs, non-HTTPS
references, and incomplete or synthetic-only evidence marked complete.

- **Native solver capability parity** counts documented solver applications,
  solver-model/source components, and numerical/physical solver capabilities
  that a CleanroomX-native solver would have to implement. Case launching,
  post-processing, tutorial replay, public API bindings, and verification
  utilities are tracked in integration or marked `na` here. A wrapper around
  an OpenFOAM executable never counts as native implementation.
- **End-to-end OpenFOAM integration coverage** counts supported app, utility,
  tutorial, API, and project integration rows. A row counts complete only
  after its integration behavior is exercised against Foundation v10; unit
  tests and synthetic fixtures alone are partial evidence.
- **Validated cleanroom engineering workflows** counts cleanroom-specific
  workflows that have implementation and engineering evidence. This requires
  reproducible real solver runs, convergence review, mesh-independence
  analysis, and independent cleanroom measurements when those gates apply.
  Synthetic data, software unit tests, or an OpenFOAM exit code alone do not
  establish physical validation.

Category subtotals use the same formula and are printed by the script. The
scores are status snapshots, not percentages of all OpenFOAM features in the
abstract; row scope and the API-inventory boundary above are part of their
meaning.

## Current scores

<!-- SCORE TABLES START -->

Matrix rows: 723

| Track | Complete | Denominator | Score |
|---|---:|---:|---:|
| Native solver capability parity | 0 | 192 | 0.00% |
| End-to-end OpenFOAM integration coverage | 0 | 717 | 0.00% |
| Validated cleanroom engineering workflows | 0 | 21 | 0.00% |

### Native solver capability parity by category

| Category | Complete | Denominator | Score |
|---|---:|---:|---:|
| Boundary conditions / basic | 0 | 6 | 0.00% |
| Boundary conditions / derived | 0 | 6 | 0.00% |
| Boundary conditions / turbulence wall functions | 0 | 5 | 0.00% |
| Boundary patch types / geometric | 0 | 9 | 0.00% |
| Finite-volume methods and algorithms | 0 | 1 | 0.00% |
| Finite-volume scheme categories | 0 | 7 | 0.00% |
| Linear solver algorithms | 0 | 6 | 0.00% |
| Mesh generation, conversion, and quality | 0 | 3 | 0.00% |
| Multi-region and coupling | 0 | 2 | 0.00% |
| Parallel execution | 0 | 3 | 0.00% |
| Solver and physical model families | 0 | 12 | 0.00% |
| Solver applications / Combustion | 0 | 6 | 0.00% |
| Solver applications / Compressible flow | 0 | 4 | 0.00% |
| Solver applications / Direct numerical simulation (DNS) | 0 | 1 | 0.00% |
| Solver applications / Discrete methods | 0 | 3 | 0.00% |
| Solver applications / Electromagnetics | 0 | 3 | 0.00% |
| Solver applications / Finance | 0 | 1 | 0.00% |
| Solver applications / Heat transfer and buoyancy-driven flows | 0 | 3 | 0.00% |
| Solver applications / Incompressible flow | 0 | 10 | 0.00% |
| Solver applications / Multiphase flow | 0 | 10 | 0.00% |
| Solver applications / Particle-tracking flows | 0 | 3 | 0.00% |
| Solver applications / Stress analysis of solids | 0 | 2 | 0.00% |
| Solver applications / ‘Basic’ CFD codes | 0 | 3 | 0.00% |
| Solver model/source components | 0 | 23 | 0.00% |
| Steady and transient algorithms | 0 | 1 | 0.00% |
| Time discretization schemes | 0 | 6 | 0.00% |
| Turbulence models / Compressible LES | 0 | 10 | 0.00% |
| Turbulence models / Compressible RAS | 0 | 14 | 0.00% |
| Turbulence models / Incompressible LES | 0 | 10 | 0.00% |
| Turbulence models / Incompressible RAS | 0 | 19 | 0.00% |

### End-to-end OpenFOAM integration coverage by category

| Category | Complete | Denominator | Score |
|---|---:|---:|---:|
| APIs, tutorials, tests, and reproducible workflows | 0 | 9 | 0.00% |
| Boundary conditions / basic | 0 | 6 | 0.00% |
| Boundary conditions / derived | 0 | 6 | 0.00% |
| Boundary conditions / turbulence wall functions | 0 | 5 | 0.00% |
| Boundary patch types / geometric | 0 | 9 | 0.00% |
| Case execution and reproducibility | 0 | 2 | 0.00% |
| Case setup and configuration | 0 | 6 | 0.00% |
| Finite-volume methods and algorithms | 0 | 1 | 0.00% |
| Finite-volume scheme categories | 0 | 7 | 0.00% |
| Linear solver algorithms | 0 | 6 | 0.00% |
| Mesh generation, conversion, and quality | 0 | 9 | 0.00% |
| Multi-region and coupling | 0 | 2 | 0.00% |
| OpenFOAM tutorial workflows | 0 | 240 | 0.00% |
| Parallel execution | 0 | 3 | 0.00% |
| Post-processing and field operations | 0 | 8 | 0.00% |
| Solver and physical model families | 0 | 12 | 0.00% |
| Solver applications / Combustion | 0 | 6 | 0.00% |
| Solver applications / Compressible flow | 0 | 4 | 0.00% |
| Solver applications / Direct numerical simulation (DNS) | 0 | 1 | 0.00% |
| Solver applications / Discrete methods | 0 | 3 | 0.00% |
| Solver applications / Electromagnetics | 0 | 3 | 0.00% |
| Solver applications / Finance | 0 | 1 | 0.00% |
| Solver applications / Heat transfer and buoyancy-driven flows | 0 | 3 | 0.00% |
| Solver applications / Incompressible flow | 0 | 10 | 0.00% |
| Solver applications / Multiphase flow | 0 | 10 | 0.00% |
| Solver applications / Particle-tracking flows | 0 | 3 | 0.00% |
| Solver applications / Stress analysis of solids | 0 | 2 | 0.00% |
| Solver applications / ‘Basic’ CFD codes | 0 | 3 | 0.00% |
| Solver model/source components | 0 | 23 | 0.00% |
| Source libraries and APIs | 0 | 94 | 0.00% |
| Standard utilities / Mesh conversion | 0 | 22 | 0.00% |
| Standard utilities / Mesh generation | 0 | 7 | 0.00% |
| Standard utilities / Mesh manipulation | 0 | 29 | 0.00% |
| Standard utilities / Miscellaneous utilities | 0 | 4 | 0.00% |
| Standard utilities / Other mesh tools | 0 | 11 | 0.00% |
| Standard utilities / Parallel processing | 0 | 4 | 0.00% |
| Standard utilities / Post-processing | 0 | 7 | 0.00% |
| Standard utilities / Post-processing data converters | 0 | 7 | 0.00% |
| Standard utilities / Pre-processing | 0 | 15 | 0.00% |
| Standard utilities / Source-tree additions | 0 | 9 | 0.00% |
| Standard utilities / Surface mesh (e.g. OBJ/STL) tools | 0 | 29 | 0.00% |
| Standard utilities / Thermophysical-related utilities | 0 | 5 | 0.00% |
| Steady and transient algorithms | 0 | 1 | 0.00% |
| Time discretization schemes | 0 | 6 | 0.00% |
| Turbulence models / Compressible LES | 0 | 10 | 0.00% |
| Turbulence models / Compressible RAS | 0 | 14 | 0.00% |
| Turbulence models / Incompressible LES | 0 | 10 | 0.00% |
| Turbulence models / Incompressible RAS | 0 | 19 | 0.00% |
| Validated cleanroom engineering workflows | 0 | 11 | 0.00% |

### Validated cleanroom engineering workflows by category

| Category | Complete | Denominator | Score |
|---|---:|---:|---:|
| Case execution and reproducibility | 0 | 2 | 0.00% |
| Post-processing and field operations | 0 | 4 | 0.00% |
| Solver and physical model families | 0 | 2 | 0.00% |
| Validated cleanroom engineering workflows | 0 | 13 | 0.00% |

<!-- SCORE TABLES END -->

## Engineering validation gate: issue #1296

Issue [#1296](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/issues/1296)
remains open. The local environment used for this review has no `blockMesh`,
`checkMesh`, `simpleFoam`, `scalarTransportFoam`, Docker, or Podman executable.
No actual Foundation v10 solver run was produced here. The existing generated
cases, logs, and grids are not substituted for measured solver evidence.

A separate GitHub Actions run [38518690225](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38518690225)
did execute Foundation v10 build `10-c4cf895ad8fa` on nine **synthetic**
layout/grid fixtures: each `blockMesh`, `checkMesh`, and `simpleFoam` stage
returned 0, and all nine `checkMesh` logs reported `Mesh OK.` The solver logs
contain 600 time entries each, but the receipts remain
`executed_requires_convergence_review`. This is genuine target-binary smoke
execution on synthetic inputs, not an engineering run or convergence result;
it closes none of the issue #1296 validation gates and is not credited as a
real cleanroom case. All 27 stage logs report `https://openfoam.org`, Version
10, and the same build identifier. The artifact was produced from branch
`codex/cfd-refinement-stable-patches-20261014` at
`4ba3b627c1e129d7f653c943106629ea6783868e`, not by the release-screening
runner changed in this proposal.

The gates remain blocked until the repository contains reproducible real v10
runs for all three layouts at coarse/medium/fine resolution; command, release,
environment, boundary-condition, input/output digest, and log evidence;
mesh-quality and solver convergence/flux-balance review; an eligible
three-grid mesh-independence analysis; model-assumption review; and
independent cleanroom airflow/pressure/particle measurements with uncertainty
and quantified comparison. Until then the workflow status remains blocked or
partial and no scientific validation claim is made.

## Verification snapshot

Local software verification used CPython 3.12.14.

```text
python scripts/openfoam_v10_parity_score.py --format json
  validated 723 unique rows and the pinned source inventory; scores: 0/192 native, 0/717 integration, 0/21 cleanroom
python -m pytest -q tests/test_cfd_pipeline.py tests/test_openfoam_v10_capability_matrix.py
  23 passed in 3.58s
python -m pytest -q
  2372 passed, 81 skipped in 388.02s on the 723-row snapshot
git diff --check
  passed
```

All 120 local implementation-path references resolved in the reviewed checkout.
The release-banner runner test uses mocked process output; it verifies screening
and receipt logic only. No local OpenFOAM executable was available, so this
software test does not establish a real solve.

## Reproduce the score

From the repository root, with Python 3.10 or newer:

```bash
python scripts/openfoam_v10_parity_score.py
python scripts/openfoam_v10_parity_score.py --format json
python -m pytest -q tests/test_openfoam_v10_capability_matrix.py
```

The matrix was reviewed against the Foundation v10 standard solver and
standard utility catalogs, the Foundation v10 user guide sections for case
setup, mesh, finite-volume methods, turbulence, parallelism, and post-process
workflows, and the pinned source inventory above. Refresh the source snapshot
and re-review every row when changing the target release.
