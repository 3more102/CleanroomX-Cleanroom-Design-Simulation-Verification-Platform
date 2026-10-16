# CleanroomX external OpenFOAM CFD pipeline

This feature generates three 3D case directories for steady incompressible
laminar flow with **OpenFOAM Foundation v10** (default) or **v14**, can opt in
to external `blockMesh`/`checkMesh` plus the release-specific solver, and
imports externally solved VTK cell fields. It provides sampled-cell
cross-section PNGs for reviewing velocity and optional scalar concentration
data. This is still an external-solver integration, not a CleanroomX CFD
solver.

The generated dictionaries use the Foundation v10 physicalProperties and
momentumTransport names. The fvSchemes file includes the viscous-stress
divergence term used by the v10 simpleFoam tutorial. These are version-specific
case-input checks; they do not replace running the generated case with the
target release.

## Educational source and limits

The uploaded NANENG 523 Lab 1 CFD handout describes three single-pass airflow
layouts and qualitatively prefers the third. It does not supply reproducible
numerical geometry, mass-flow boundary conditions, mesh convergence data,
material properties, solver logs, contamination-source rate or acceptance
criteria. **None of these is invented by CleanroomX.** Example parameters are
SYNTHETIC functional smoke test values only.

Configuration 1 has central ceiling supply and low-wall exhaust;
Configuration 2 has distributed ceiling supply and low-wall exhaust;
Configuration 3 has distributed ceiling supply and a perforated-floor
effective exhaust boundary. The underfloor plenum and perforation hydraulics
are **not resolved**. No internal furniture/FFUs/obstacles are modeled.

## Install / generate / run

In Python 3.11+:

    pip install -e '.[cfd]'

Generate all three cases without OpenFOAM installed:

    cleanroomx-cfd-pipeline generate examples/cfd_openfoam_spec.example.json ./cfd_cases

Generate a Foundation v14 case bundle explicitly:

    cleanroomx-cfd-pipeline generate examples/cfd_openfoam_spec.example.json ./cfd_cases_v14 --openfoam-version v14

Inspect the resulting system, constant, and 0 field files. The manifest binds
each generated input using SHA-256; existing output directories are not
overwritten. Supply airflow is imposed by downward velocity determined from
each configuration's explicit inlet patch area.

For the default v10 bundle, install OpenFOAM Foundation v10 on Linux/WSL,
source that installation's `etc/bashrc` in the environment that starts
CleanroomX, and put `blockMesh`, `checkMesh` and `simpleFoam` on PATH. The
runner requires `WM_PROJECT=OpenFOAM`, `WM_PROJECT_VERSION=10`, and a matching
`OpenFOAM-10` solver version banner. It also checks each successful stage log
for the Foundation site, Version 10, and a nonempty build ID shared by every
stage and layout. It records parsed identity, executable paths, commands,
input hashes, exit codes, and log hashes in `run_manifest.json`; an identity
mismatch marks the run incomplete and stops it. These checks cover the three
generated layouts; the separate nine-case, three-grid evidence required by
issue #1296 remains outstanding. Then opt in:

    cleanroomx-cfd-pipeline run ./cfd_cases --timeout-seconds 3600

For a v14 bundle, install the pinned OpenFOAM Foundation v14 release, source
that installation's `etc/bashrc`, and put `blockMesh`, `checkMesh` and
`foamRun` on PATH. The runner requires `WM_PROJECT=OpenFOAM`,
`WM_PROJECT_VERSION=14`, and an `OpenFOAM-14` solver version banner:

    cleanroomx-cfd-pipeline run ./cfd_cases_v14 --openfoam-version v14 --timeout-seconds 3600

The v14 files use the documented `solver incompressibleFluid` case selector,
`physicalProperties` and `momentumTransport` dictionaries. The v10 nine-case
grid workflow used by issue #1296 remains pinned to v10. The v14 generator and
runner have generated-dictionary and mocked-command tests only in this
environment; there is no real v14 solver execution evidence here.

The runner checks input hashes, uses no shell, verifies the active Foundation
release and solver banner, and writes `run_manifest.json` with the exact
executable paths, commands, version probe, input hashes, exit codes and log
hashes. It refuses to overwrite a previous run manifest or solver logs. This
local manifest is provenance evidence, not an immutable external archive. A
zero return code is **not CFD convergence**: inspect residuals, continuity,
boundary flux balance, turbulence/Reynolds applicability, mesh quality and
grid independence. The v14 case template selects the `incompressibleFluid`
module through `foamRun`, following the v14 case configuration.

## Import actual CFD results (VTK/VTU)

Export solved fields with your OpenFOAM installation's foamToVTK utility,
or an equivalent CFD package that produces an unstructured grid. Prepare a
CleanroomX cfd-study v1 JSON with explicitly verified room dimensions,
source coordinates, design limits, fluxes and matched boundary conditions.

    cleanroomx-cfd-pipeline import-vtk study.json \
      --case-1 c1.vtu --case-2 c2.vtu --case-3 c3.vtu \
      --solver-name 'OpenFOAM v10' --output evaluated.json

Required field: three-component U in m/s, available at cell or point level.
Real cell volumes are computed from the VTK mesh. Optional cell scalar T is
the externally solved contaminant concentration; optional externally computed
binary mask recirculating is required for recirculation metric. SHA-256 hashes
bind raw VTK sources. NaNs, invalid volumes/concentration, changed inputs and
oversized sources fail. Missing scalar/recirculation/flow evidence blocks a
three-case winner. This feature **does not solve scalar transport**.

## Compare visualized cell samples

    cleanroomx-cfd-pipeline plot \
      --case-1 c1.vtu --case-2 c2.vtu --case-3 c3.vtu \
      --field speed --axis y --position-m 1 --slab-thickness-m 0.25 \
      --output velocity-slab.png

This displays cell-center samples inside a finite-thickness slab; it is not
an interpolated CFD contour or velocity streamline. The plot does not certify
CFD, ISO classification, or any regulatory qualification.

## Engineering follow-on gates

A full physically validated CFD system needs real CAD/IFC boundary geometry,
diffusers, fan/filter and perforated-tile hydraulics, turbulence and buoyancy,
particle/scalar transport with true source terms, sensitivity/refinement
studies, solver residual/flux convergence, onsite measurements, full GUI
integration, dossier and ProofGraph evidence. The exporter is intentionally
bounded to 20,000 hexahedral cells for a reproducible first solver pipeline,
not as a declared mesh-accuracy target.

Release-specific baseline references:
- OpenFOAM Foundation v10 [pitzDaily physicalProperties](https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/tutorials/incompressible/simpleFoam/pitzDaily/constant/physicalProperties), [momentumTransport](https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/tutorials/incompressible/simpleFoam/pitzDaily/constant/momentumTransport) and [fvSchemes](https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/tutorials/incompressible/simpleFoam/pitzDaily/system/fvSchemes).
- OpenFOAM Foundation v10 [`etc/bashrc`](https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/etc/bashrc), [turbulence guide](https://doc.cfd.direct/openfoam/user-guide-v10/turbulence) and [scalarTransportFoam source](https://cpp.openfoam.org/v10/scalarTransportFoam_8C_source.html).
- OpenFOAM Foundation v14 [release notes](https://openfoam.org/release/14/) and [tagged source](https://github.com/OpenFOAM/OpenFOAM-14/tree/version-14).
- OpenFOAM Foundation v14 [pitzDailySteady controlDict](https://github.com/OpenFOAM/OpenFOAM-14/blob/version-14/tutorials/incompressibleFluid/pitzDailySteady/system/controlDict).

OpenFOAM.com documentation describes a separately maintained distribution
and is not used as the parity baseline for either Foundation release.

See the separate [Foundation v10 capability matrix](OPENFOAM_FOUNDATION_V10_PARITY.md)
and [pinned v14 capability matrix and scores](OPENFOAM_V14_PARITY.md).
