# CleanroomX external OpenFOAM CFD pipeline

This feature generates three 3D case directories for **OpenFOAM Foundation
v10** steady incompressible laminar flow, optionally executes the external
blockMesh/checkMesh/simpleFoam programs, and imports independently solved VTK
cell fields. It provides sampled-cell cross-section PNGs for reviewing velocity
and optional scalar concentration data.

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

Each case manifest includes an input-only boundary audit. It reads the
generated `blockMeshDict` face coordinates, derives the complete exterior-face
set from its hex blocks, and requires each exterior face exactly once across
the patches. Duplicate, omitted, internal, non-manifold, or unsupported block
faces are rejected. It recomputes inlet/outlet areas and
outward normals, checks the generated `U`/`p` patch-condition types, and
integrates the prescribed inlet velocity over the inlet faces against the
requested supply flow. The audit records the outlet solver flux as
`not_measured`, the flow balance as `not_measured`, and scientific validation
as `BLOCKED`. It does not establish that the example room, patch placement,
or requested flow matches a real cleanroom, and it does not replace reviewing
the solver's actual inlet/outlet `phi` after execution.

Inspect the resulting system, constant, and 0 field files. The manifest binds
each generated input using SHA-256; existing output directories are not
overwritten. Supply airflow is imposed by downward velocity determined from
each configuration's explicit inlet patch area.

Install OpenFOAM Foundation v10 on Linux/WSL and source its `etc/bashrc` so
`WM_PROJECT=OpenFOAM` and `WM_PROJECT_VERSION=10`; keep `blockMesh`,
`checkMesh`, and `simpleFoam` on PATH. The runner checks those environment
markers, then verifies each executable's log banner identifies
`https://openfoam.org`, Version 10, and one consistent build. It records the
resolved executable paths and build identifier. For `checkMesh`, it also
records a hash-bound structured diagnostic summary of mesh counts, cell types,
bounding box, areas, volumes, and the geometric checks printed by OpenFOAM.
The summary copies the tool's reported result but sets project acceptance to
`not_assessed_no_project_criteria`; it never applies invented quality limits.
The runner stops before `simpleFoam` if the Foundation v10 report is incomplete
or `checkMesh` reports failure. Other OpenFOAM distributions and releases are
rejected by this v10 case runner. Then opt in:

    cleanroomx-cfd-pipeline run ./cfd_cases --timeout-seconds 3600

The runner checks input hashes, recomputes the boundary audit from the bound
case files, returns those audit records with its execution receipt, uses no
shell and records solver logs. A zero
return code is **not CFD convergence**: inspect residuals, continuity,
boundary flux balance, turbulence/Reynolds applicability, mesh quality and
grid independence. Other OpenFOAM versions may require solver template
changes: v11+ Foundation uses foamRun solver modules.

See [OpenFOAM checkMesh diagnostics](OPENFOAM_CHECKMESH_DIAGNOSTICS.md) for the
receipt schema, parser behavior, and the distinction between reported
`checkMesh` checks and project-defined mesh acceptance.

The GitHub nine-case Foundation v10 workflow additionally requires
`foamToVTK`. After each successful `simpleFoam` run, it exports the latest
cell velocity `U`, kinematic-pressure `p`, and surface flux `phi` with ASCII
output, imports the cell dataset, and binds its hash and cell count to the
generated-input manifest. It then reopens and verifies all nine outputs before
uploading the evidence artifact.
This workflow export is a reproducibility and ingestion check; it is not part
of the standalone `run` command and does not establish CFD convergence,
mesh independence, or physical validation.

The nine-case v10 workflow compares exported cell velocity and kinematic
pressure with the native final-time OpenFOAM `U` and `p` fields. It uses the
`cellID` cell-data array
written by Foundation v10 `foamToVTK`: the upstream
[`internalWriter::writeCellIDs` implementation](https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/applications/utilities/postProcessing/dataConversion/foamToVTK/foamToVTK/internalWriter.C)
emits the original mesh cell index for every cell. CleanroomX requires a
complete, unique ID mapping and compares each U component and p scalar by that
ID; it does not infer cell correspondence from VTK array order. The U audit
requires cell-data `U`, so it cannot silently substitute point-to-cell
interpolation. The p audit requires a native `volScalarField` with kinematic-
pressure dimensions `[0 2 -2 0 0 0 0]` and a scalar cell-data `p` array.

Foundation v10's legacy VTK output declares these U and p arrays as `float`.
The parity receipt reports measured component/scalar errors and bounds them
using binary32 rounding plus half a last decimal place at the workflow's
six-digit ASCII precision. These tolerances describe field serialization only;
they are not CFD solver acceptance thresholds and provide no convergence or
physical validation evidence.

The workflow also requests `foamToVTK -surfaceFields` for the native
`surfaceScalarField phi`. In the pinned Foundation v10 implementation,
[`foamToVTK.C`](https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/applications/utilities/postProcessing/dataConversion/foamToVTK/foamToVTK.C)
converts each scalar flux to `phi` times the oriented unit face normal, and
[`writeSurfFields.C`](https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/applications/utilities/postProcessing/dataConversion/foamToVTK/foamToVTK/writeSurfFields.C)
serializes those values with the mesh face centres in face order. CleanroomX
reconstructs face centres and normals from the archived `polyMesh`, checks the
serialized centre sequence, and compares all three vector components within
the float32/ASCII bounds. This checks the v10 export representation for the
synthetic mesh family; it does not set a flow-balance criterion or establish
solver convergence or physical validity.

The Foundation v10 integration workflow makes a separate multi-time export
using `foamToVTK -time 50,100 -useTimeName`. It requires the utility log to
show exactly the requested `50` and `100` times in order, then compares the
exported internal U/p, inlet/outlet/walls U/p, and surface `phi` datasets with
the native fields in each matching time directory. The v2 sidecar receipt
binds the command log, source fields, and every selected-time VTK file by
SHA-256. The selected times avoid the baseline latest-time output at `150` and
cover two exact times from the synthetic three-output case. This does not
establish arbitrary time-range support, solver convergence, or physical
validation. The pinned upstream [`foamToVTK.C`](https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/applications/utilities/postProcessing/dataConversion/foamToVTK/foamToVTK.C)
registers comma-separated time ranges, iterates the selected time directories,
and uses `-useTimeName` to name each dataset from the solver time name.

Foundation v10 run 94 completed this `50,100` audit for all nine synthetic
cases. Its [multi-time report](OPENFOAM_V10_RUN_38872039438_MULTI_TIME_VTK_AUDIT.md)
records 18 case-time pairs and 108 passing internal, patch, and surface-flux
parity records. Independent replay matched all 72 generated-input hashes, 36
baseline stage-log hashes, the manifest and execution-receipt hashes, and all
153 selected-time file records. The artifact SHA-256 is
`fa5b85af0e8ed2470101747540f22808032ba1959c0f41548551b62a24f060a3`.
The results remain `DIAGNOSTIC_ONLY`; scientific validation remains `BLOCKED`.

Run 90 applied this audit to all nine generated cases. Its 54 internal-field, patch, and surface-flux parity records passed, including 13,608 patch faces. The [run 90 report](OPENFOAM_V10_RUN_38867911839_VTK_TIME_SELECTION.md) records the independent artifact-digest and file-hash replay. Residual and flow-balance screens remain diagnostic; scientific validation remains BLOCKED.

The independently rechecked run 58 U archive and per-case native/VTK hashes
are recorded in [the run 58 parity report](OPENFOAM_V10_RUN_38694132081_NATIVE_VTK_PARITY.md).
Run 61 extends that check to native final-time `U` and `p`; its artifact,
per-case errors, and independent digest checks are recorded in [the run 61
U/p parity report](OPENFOAM_V10_RUN_38768856636_NATIVE_U_P_VTK_PARITY.md).

Run 63 also checks the separate `inlet`, `outlet`, and `walls` patch surfaces.
It maps VTK faces to native boundary faces by serialized point geometry, checks
`patchID` and full face coverage, and compares patch U/p against native
boundary-field values. The workflow covers 27 patch datasets, 13,608 faces,
40,824 velocity components, and 13,608 pressure values; the independent
artifact recheck and per-patch errors are in [the run 63 patch-parity report](OPENFOAM_V10_RUN_38772855917_NATIVE_VTK_PATCH_PARITY.md).
This verifies only the current synthetic single-region family and its present
boundary-condition types; it does not add patch surfaces to volume-weighted
cleanroom metrics.

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
https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/tutorials/incompressible/simpleFoam/pitzDaily/constant/physicalProperties
https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/tutorials/incompressible/simpleFoam/pitzDaily/constant/momentumTransport
https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/tutorials/incompressible/simpleFoam/pitzDaily/system/fvSchemes
https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/etc/bashrc
https://doc.cfd.direct/openfoam/user-guide-v10/turbulence
https://cpp.openfoam.org/v10/scalarTransportFoam_8C_source.html
