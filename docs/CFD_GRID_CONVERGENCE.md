# CFD three-grid refinement and GCI screening

## Capability and status

CleanroomX can generate **nine** OpenFOAM Foundation v10 cases (three room
ventilation configurations x coarse/medium/fine grid) without solving them.
It can then read **three actual VTK files plus three solver logs** for one
ventilation configuration and compute a volume-weighted quantity of interest
(QoI), observed order of convergence, Richardson extrapolation and Roache's
fine-grid Grid Convergence Index (GCI).

The analysis is a **numerical screening tool**. A small GCI does not prove
the discretized model represents the physical cleanroom, and three grid
levels alone do not independently prove asymptotic convergence.
The uploaded NANENG 523 document provides no numerical mesh convergence
results; this feature does not invent them.

## Generate three mesh levels

Use a clearly synthetic sample (replace every physical parameter before
engineering use):

    cleanroomx-cfd-pipeline grid-generate \
      examples/cfd_grid_family.example.json ./cfd_mesh_family

Output folders: configuration_1/coarse, configuration_1/medium,
configuration_1/fine, and the same three levels for configurations 2 and 3.
Each contains system, constant, and 0 solver input dictionaries. SHA-256
digests are generated for all 72 inputs. Existing destinations are not
overwritten. Each case can be run using blockMesh, checkMesh and simpleFoam
in its individual case directory. The generator does not itself run any
solver, does not prove physical mesh quality, and retains the current
per-case 20,000-cell bound.

## Evaluate VTK fields from three completed flow runs

Use the separate example template for one ventilation configuration. Copy
three real cell-based .vtu/.vtk datasets and corresponding solver log files
into the same directory as the JSON study manifest. Populate all fields:
each grid's actual dimensions and identifiers, the actual same physical
and boundary-condition fingerprint, user-selected log residual acceptance
criteria, selected flow QoI, and required volume tolerance.

    cleanroomx-cfd-pipeline grid-audit my_grid_study.json \
      --output my_grid_audit.json

The CLI resolves input dataset paths relative to the study JSON. VTK and
solver-log paths must be relative, must resolve to files **within the study
JSON's directory**, and may refer to nested directories. Absolute paths,
parent-directory escapes, and symbolic links resolving outside that root are
rejected before the external data is imported. This is a location check at
resolution time, not a guarantee against concurrent filesystem mutation.
Currently supported QoIs:

- velocity_mean_m_s: volume-weighted cell-centered |U|, in m/s
- contaminant_mean: volume-weighted externally solved T (project units)

The VTK importer hashes the exact file bytes; the independent log audit
hashes the raw residual log. The grid audit rejects byte-identical VTK datasets
or solver logs replayed across resolution levels, even if the file names differ.
This is an evidence-integrity screen, not proof that separately hashed runs
used identical physical conditions. Sample volumes must represent the room within
the project-defined tolerance. The reported mesh cell count must agree with
the user's declared 3D grid dimensions. Each mesh axis must increase as the
grid is refined, with comparable axis refinement ratios. The declared
conditions hashes must match, although this **does not independently prove**
identical solver settings, inlet BCs, turbulence closure, or convergence.

Only monotone three-grid trends yielding positive observed order are eligible
for Richardson extrapolation and GCI. Oscillatory, flat or otherwise
unsupported trends yield an **indeterminate** result. No GCI percentage is
computed when the finest-grid QoI is zero. The selected GCI threshold,
admissible order, and log residual criteria are **project inputs**, not
inferred regulatory thresholds.

## Calculations and interpretation

For a common 3D domain volume V, with cell counts N and effective
characteristic lengths h=(V/N)^(1/3), ordered finest to coarsest:

- r21=h2/h1 and r32=h3/h2
- f(h)=f0+A*h^p with an observed p determined numerically, including
  unequal refinement factors
- zero-spacing extrapolate f0=f1+(f1-f2)/(r21^p-1)
- fine GCI (%)=100*Fs*|f2-f1|/(|f1|*(r21^p-1))

For three grid levels, the documented NASA/Roache practice uses
a typical safety factor Fs=1.25; CleanroomX requires Fs>=1.25, set by
the engineering project. It does not infer asymptotic verification from an
algebraic fit to exactly three points; an independent fourth grid or
additional grid studies can be necessary to justify that assumption.

The regression tests include NASA Glenn's published
pressure-recovery benchmark (0.97050, 0.96854, 0.96178 with 1:2:4 grid
spacing), whose GCI is approximately 0.10308% and apparent order
approximately 1.78617. Synthetic VTK meshes are used for separate full
field-import end-to-end tests. **These are software numerical regression
fixtures, not measured cleanroom results.**

Even an eligible result must be reviewed for solver residual and mass-flux
closure, physical/BC consistency, mesh quality, source selection,
wall treatment, turbulence modeling, grid family adequacy, validation
against measurements and relevant design/qualification requirements.

## Standalone solver-log triage (read-only)

For an actual completed OpenFOAM Foundation-style simpleFoam.log, run:

    python -m cleanroomx.cfd_convergence_triage \
      path/to/simpleFoam.log --fields Ux Uy Uz p --window 5

The command reads up to 64 MiB of UTF-8 log data without invoking OpenFOAM.
It reports a SHA-256 of the input log bytes, solver residual history, recent
global continuity errors, a count of time steps, and observations about the
final time step. It fails closed for missing or repeated terminal End markers,
fatal/nonfinite tokens, negative residuals, invalid or non-increasing time
stamps, missing required fields or continuity in **any** time step, malformed
solver/continuity records, and solver records preceding the first time stamp.
The `incomplete_prior_time_steps` count detects incomplete earlier steps
even when the final step is complete. Both the log and its parent directories
must not be symbolic links; this is not protection against concurrent path
replacement.

Exit code 0 means the log met these **diagnostic parsing conditions** only;
exit code 3 means the log was incomplete or invalid. Both outcomes keep
scientific_validation=BLOCKED. Neither a small final linear-system residual
nor a DIAGNOSTIC_ONLY label verifies nonlinear convergence, mass/particle
balance, mesh independence, physical accuracy, independent execution, or
compliance with a cleanroom standard.

The CLI does **not** automatically inspect every log in the nine-case grid
family. Project-specific convergence tolerances, trusted solver provenance,
independent mesh and boundary-condition checks, and comparison against
measured cleanroom data are separately required under issue #1296.

## References

- NASA Glenn Research Center, *Examining Spatial (Grid) Convergence*:
  https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html
- NASA CFD verification and validation tutorial:
  https://www.grc.nasa.gov/www/wind/valid/tutorial/tutorial.html
