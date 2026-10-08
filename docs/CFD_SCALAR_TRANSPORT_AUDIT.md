# Passive tracer + numerical residual audit (OpenFOAM Foundation v10)

This workflow extends the CleanroomX CFD case generator. It is an **external OpenFOAM
v10 computation and numerical-screening interface**, not a validated particle
dispersal model, regulatory certification, calibrated contamination simulation,
or independent verification of mass conservation.

## Physics (independently checked against OpenFOAM Foundation v10 source)

OpenFOAM Foundation v10's `scalarTransportFoam` reads scalar `T`, velocity
`U`, and diffusivity `DT` from `constant/physicalProperties`, then solves
the passive-scalar advection/diffusion equation with `fvModels` sources.
CleanroomX uses the built-in `semiImplicitSource`, selecting the mesh cell
that contains a user-specified interior source point. The source is an
**absolute integrated injection strength** with a dimensionless tracer
field `T`; `source_strength_m3_s` is an illustrative tracer-volume source
amplitude, not a particles/s, biological dose or calibrated emission.

CleanroomX generates `constant/fvModels`, `constant/physicalProperties`,
`0/T`, `system/controlDict`, `system/fvSchemes`, and `system/fvSolution`.
The generated scalar case reuses a copied *nonzero-time computed* airflow
`U` and polyMesh, not the initial zero-velocity field. Every input file
is hashed in a stable local manifest; no existing output is overwritten.

## Running

Install CleanroomX from the current checkout. First, use the existing CFD
generator and install/configure OpenFOAM Foundation v10 in Linux/WSL.
Run each airflow configuration and inspect flow residuals and mass balance.

    cleanroomx-cfd-pipeline generate examples/cfd_openfoam_spec.example.json ./cfd_cases
    cleanroomx-cfd-pipeline run ./cfd_cases

Prepare and run a scalar case from each **completed airflow** case:

    cleanroomx-cfd-pipeline scalar-prepare ./cfd_cases/configuration_1 examples/cfd_scalar_spec.example.json ./scalar_1
    cleanroomx-cfd-pipeline scalar-run ./scalar_1

Repeat for configurations 2 and 3 with separate output directories. This
does **not** automatically assert convergence or equal physical boundary
conditions. The example inputs are synthetic and must be replaced.

## Screen numerical logs

All tolerances are supplied by your project; no ISO threshold is assumed.
Example for airflow:

    cleanroomx-cfd-pipeline audit-log ./cfd_cases/configuration_1/simpleFoam.log --fields Ux Uy Uz p --max-initial-residual 1e-5 --max-final-residual 1e-7 --max-global-continuity 1e-6 --window 3

Example for scalar transport:

    cleanroomx-cfd-pipeline audit-log ./scalar_1/scalarTransportFoam.log --fields T --max-initial-residual 1e-5 --max-final-residual 1e-7 --window 3

The audit checks field-specific recent initial/final linear solver residuals,
terminal End marker, fatal/nonfinite markers and optionally the reported
global continuity error. It fails closed on missing evidence. A pass says
only that **the supplied numerical log-screen criteria passed**, not that
physical CFD convergence, mesh independence or a cleanroom qualification
was established. Log measures are not an independently integrated flux
or contamination source/sink balance.

## Explicit limitations

- No OpenFOAM executable is bundled or run within CI; CI verifies generation,
  mock execution, input integrity and numerical parsing.
- One grid cell is selected per source point; mesh refinements change source
  localization. Grid convergence and source-cell sensitivity are required.
- The steady laminar, incompressible flow assumption can be unsuitable for
  real cleanrooms; this is not a turbulence closure, FFU model or plenum CFD.
- The output T is a normalized tracer without particle inertia, deposition,
  coagulation, Brownian particle physics, filter removal or calibrated particle
  counts. It cannot support an ISO class assertion.
- Check real OpenFOAM logs for errors and confirm model dictionary compatibility
  with the installed Foundation release before engineering reliance.

## Primary authoritative code references

- https://cpp.openfoam.org/v10/scalarTransportFoam_8C_source.html
- https://cpp.openfoam.org/v10/solvers_2basic_2scalarTransportFoam_2createFields_8H_source.html
- https://cpp.openfoam.org/v10/semiImplicitSource_8H_source.html
- https://cpp.openfoam.org/v10/fvCellSet_8C_source.html
