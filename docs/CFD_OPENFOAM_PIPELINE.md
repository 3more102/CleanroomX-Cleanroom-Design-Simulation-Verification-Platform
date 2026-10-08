# CleanroomX external OpenFOAM CFD pipeline

This feature generates three 3D case directories for **OpenFOAM Foundation
v10** steady incompressible laminar flow, optionally executes the external
blockMesh/checkMesh/simpleFoam programs, and imports independently solved VTK
cell fields. It provides sampled-cell cross-section PNGs for reviewing velocity
and optional scalar concentration data.

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

Inspect the resulting system, constant, and 0 field files. The manifest binds
each generated input using SHA-256; existing output directories are not
overwritten. Supply airflow is imposed by downward velocity determined from
each configuration's explicit inlet patch area.

Install OpenFOAM Foundation v10 on Linux/WSL and put blockMesh, checkMesh and
simpleFoam on PATH. Then opt in:

    cleanroomx-cfd-pipeline run ./cfd_cases --timeout-seconds 3600

The runner checks input hashes, uses no shell and records solver logs. A zero
return code is **not CFD convergence**: inspect residuals, continuity,
boundary flux balance, turbulence/Reynolds applicability, mesh quality and
grid independence. Other OpenFOAM versions may require solver template
changes: v11+ Foundation uses foamRun solver modules.

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

OpenFOAM references:
https://doc.openfoam.com/2306/tools/processing/solvers/rtm/incompressible/simpleFoam/
https://doc.openfoam.com/2606/quickstart/
https://cpp.openfoam.org/v10/scalarTransportFoam_8C_source.html
https://doc.cfd.direct/openfoam/user-guide-v13/solvers-modules
