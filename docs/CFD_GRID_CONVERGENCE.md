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

The reproducible GitHub Foundation v10 workflow now executes all nine
synthetic cases with `blockMesh`, `checkMesh`, `simpleFoam`, and
`foamToVTK`. For each case it exports final-time cell velocity `U` and
kinematic-pressure `p`, imports the internal-cell VTK through CleanroomX,
checks its cell count against the generated-input manifest, and records source
hashes in the execution receipt. It also audits the separate inlet, outlet,
and wall patch surfaces against the native mesh faces and final-time U/p
boundary fields. A post-run integrity pass reopens all nine internal datasets
and all 27 patch datasets, then rechecks their paths, hashes, field counts,
and serialized values before uploading a summary.

The [run 63 report](OPENFOAM_V10_RUN_38772855917_NATIVE_VTK_PATCH_PARITY.md)
records the patch mapping method, all 13,608 compared boundary faces, and the
independent artifact recheck.

The [run 66 checkMesh report](OPENFOAM_V10_RUN_38776224839_CHECKMESH_QUALITY.md)
records topology and geometric quality diagnostics from the nine archived
Foundation v10 logs. These regular synthetic meshes have no project-defined
quality acceptance thresholds and do not establish suitability for a physical
cleanroom geometry.

The [run 67 execution report](OPENFOAM_V10_RUN_38777678904_GRID_EVIDENCE.md)
records all 36 successful OpenFOAM command stages, the boundary-input audit,
per-case solver and VTK digests, and the residual/flux screens. Its output
remains diagnostic: U/p residual screening did not pass, and no project
flow-balance criterion or independent physical measurements are available.

The [run 66 residual-history report](OPENFOAM_V10_RUN_38776224839_RESIDUAL_TREND.md)
records all nine cases' terminal residual-to-setting multiples and compares
early/late log medians. Every case remains above the generated residual screen;
the analysis is descriptive and does not diagnose a physical cause.

The runner now records a structured, raw-log-hash-bound `checkMesh` summary
and stops before `simpleFoam` when required Foundation v10 records are missing,
ambiguous, non-finite, or report a failed check. It applies no project mesh
acceptance thresholds; see [the diagnostic receipt guide](OPENFOAM_CHECKMESH_DIAGNOSTICS.md).
The Foundation v10 workflow also receipt-binds each `checkMesh.log` digest,
reconstructs every cell volume from the ASCII `polyMesh` points, faces, owner,
and neighbour lists, and compares cell counts, minimum/maximum/total volumes,
the reconstructed bounding-box volume, and manifest-derived room volume. The
uploaded `poly_mesh_volume_audit.json` records the five mesh-file hashes and
the comparison tolerances. CheckMesh rounding bounds come from the longest
numeric precision present in its volume summary; floating-point bounds cover
the reconstruction arithmetic using `128 × binary64 epsilon ×
max(1, |value|)`. These are serialization and arithmetic tolerances only, not
CFD acceptance thresholds. The audit checks consistency of the synthetic mesh
evidence; it does not establish mesh quality, numerical convergence, or
physical suitability.

This verifies solver execution and VTK ingestion for that synthetic run only.
It does not make the residual or flux screens pass, establish mesh independence,
or change scientific validation from `BLOCKED`. The workflow does not yet
compute GCI automatically; use the existing GCI analysis only after the
convergence and physical-input gates below are met.

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

Each case manifest also contains an input-only boundary audit. It recomputes
patch face areas and outward normals from `blockMeshDict`, checks the generated
velocity and pressure patch types, and verifies that prescribed inlet normal
velocity integrates to the input supply flow. The audit records the actual
outlet solver flux and flow balance as `not_measured`; it does not assert that
the synthetic geometry or flow represents a real cleanroom.

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

## Review the final solver volume flux

When each case contains a `phi` field at the last time reported in its
`simpleFoam.log`, `cleanroomx-cfd-grid-triage FAMILY` also reads the signed
patch fluxes and the `nFaces` counts from `constant/polyMesh/boundary`. The
Foundation v10 incompressible solver constructs `phi` from `fvc::flux(U)` in
its pinned [`createPhi.H`](https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/src/finiteVolume/cfdTools/incompressible/createPhi.H).
The report records net inlet inflow, net outlet outflow, reverse flow on
either patch, wall flux, total boundary flux, and relative flux imbalance.

This result is `MEASURED_DIAGNOSTIC_ONLY`. CleanroomX does not supply an
acceptance threshold: the report says `NO_PROJECT_ACCEPTANCE_CRITERION` until
the engineering project defines one. The screen is separate from residual
status and does not establish nonlinear convergence, mesh independence,
physical validity, or cleanroom performance. Missing, malformed, or
unreadable final-time fields remain unavailable without changing the log
triage status.

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
      path/to/simpleFoam.log --fields Ux Uy Uz p --window 5 --trend-window 50

The command performs a bounded read of at most 64 MiB plus one guard byte
of UTF-8 log data without invoking OpenFOAM, including when the log grows
after an initial file-size check. Before accepting parsed bytes, it compares
the source path's device/inode identity, size and nanosecond modification time
before and after reading, and rechecks whether any path component became a
symbolic link. A detected replacement or mutation fails with
`log changed during diagnostic read`. This is a conservative filesystem
consistency check, not atomic snapshotting or authenticated provenance:
concurrent edits may still evade metadata comparisons.
It retains only the requested recent
`--window` residual and global-continuity values plus the first and last
`--trend-window` initial residuals per requested field, while preserving
the total counts, latest time stamp, and full-log SHA-256. The compared trend
windows are disjoint; for shorter logs, both shrink to at most half the
available samples. Both windows are bounded to 10,000 samples;
`--trend-window` defaults to 50. It maintains only
a running time-step count instead of a separate list of all time stamps,
and reuses its parsed line list to find the final nonblank `End`.
Input bytes and decoded text are still materialized under the 64 MiB cap. It reports solver residual history, recent
global continuity errors, a count of time steps, and observations about the
final time step. It fails closed for missing or repeated terminal End markers,
fatal/nonfinite tokens, negative residuals, invalid or non-increasing time
stamps, malformed or skipped `Time =` markers, missing required fields or
continuity in **any** time step, and malformed solver/continuity records
(including appended content or unbounded iteration integers). Trailing
whitespace on otherwise valid records is allowed. Solver records preceding
the first time stamp remain an error.
Foundation logs that report time in seconds as `Time = 12s` are accepted
alongside unitless numeric stamps. The startup notice
`sigFpe : Enabling floating point exception trapping` is not treated as a
solver failure; an actual `Floating point exception` error line still fails
closed.

When a Foundation log prints a single `SIMPLE: Convergence criteria found`
block, the report also includes `terminal_residual_control_screen`. It reads
the displayed field tolerances and compares them with the last time step's
logged initial linear residuals using OpenFOAM's strict `<` boundary. For a
configured vector `U`, the screen uses the maximum of the logged `Ux`, `Uy`,
and `Uz` initial residuals as a conservative component proxy. This is not the
solver's internal vector `residualControl` value or a nonlinear convergence
decision. Missing, repeated, malformed, or ambiguous criteria/terminal records
produce `UNKNOWN`; the screen never changes `scientific_validation=BLOCKED`.

The `residual_trend` record compares the median initial linear residual in the
first and last disjoint windows for each requested field. Each window uses
`min(--trend-window, floor(sample_count / 2))` samples so short logs never
compare overlapping records. It reports both medians and their ratio, with
`INSUFFICIENT_SAMPLES` when fewer than two records exist and
`ZERO_INITIAL_MEDIAN` when a ratio would divide by zero. A ratio that
overflows to a non-finite value is reported as `NONFINITE_RATIO`. The trend is
descriptive only: a ratio below one means the selected tail median is lower
than the selected initial median. It has no pass/fail
threshold and does not show monotonic reduction, reproduce vector `U`
residualControl, establish solver convergence, or change the blocked
scientific-validation status.

Descriptive trend analyses of the archived synthetic Foundation v10 runs 67
and 68, including per-case medians and ratios, are recorded in the
[run 67 report](OPENFOAM_V10_RUN_38777678904_RESIDUAL_TREND.md) and the
[run 68 report](OPENFOAM_V10_RUN_38779101381_RESIDUAL_TREND.md).

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

When the standalone CLI receives multiple log paths, it rejects byte-identical
files across distinct input paths with `DUPLICATE_LOG_BYTES` and rejects
repeated input paths with `DUPLICATE_INPUT_PATH`, including lexical aliases
such as relative versus absolute paths or `./` components; either case returns
exit code 3. Aliased path names are included in `duplicate_input_paths`. Individual SHA-256 digests are retained in the JSON
report and duplicate source paths are listed. Identical bytes are ambiguous
execution evidence, not proof of intentional replay; different bytes do not
establish independent executions. The CLI does **not** automatically inspect
every log in the nine-case grid family. Project-specific convergence
tolerances, trusted solver provenance,
independent mesh and boundary-condition checks, and comparison against
measured cleanroom data are separately required under issue #1296.

## Triage all nine solver logs

Use the read-only family command after the nine Foundation v10 runs have
completed:

    cleanroomx-cfd-grid-triage ./cfd_mesh_family --window 5 --trend-window 50

It reads only the expected
`configuration_1..3/{coarse,medium,fine}/simpleFoam.log` files and writes a
per-case JSON report. Missing, malformed, byte-identical, or unexpected
`simpleFoam.log` files fail closed. The optional fields and recent-sample
window have the same limits as the single-log diagnostic.

The family report also includes `solver_input_fingerprint_screen`. It hashes
the bytes of seven declared solver-condition dictionaries in every case:
`0/U`, `0/p`, `constant/physicalProperties`,
`constant/momentumTransport`, `system/controlDict`, `system/fvSchemes`, and
`system/fvSolution`. It compares those hashes across coarse/medium/fine within
each configuration. `system/blockMeshDict` is hashed separately because grid
geometry inputs are expected to vary. Missing, unreadable, symlinked, changed
during reading, or over-16-MiB input files are reported as
`INCOMPLETE_OR_UNREADABLE`; a condition dictionary mismatch is reported as
`DIFFERENT_ACROSS_GRID_LEVELS`.

This is a byte-consistency screen for the declared files. Matching hashes do
not prove boundary-condition correctness, actual patch areas or flow rates,
geometry equivalence, independent execution, mesh independence, physical
convergence, or model validity. The input screen does not alter the top-level
log status or CLI exit code: exit code 0 still means only that all nine logs
were structurally parseable and distinct by byte digest. Review both screens
separately before using a family for a numerical comparison.

Exit code 0 means all nine logs were structurally parseable and distinct by
byte digest. It does **not** mean the configured residual screen passed.
`configured_residual_screen` separately reports whether each case's logged
Foundation `U` and `p` initial residuals are below the tolerances shown in
its log. The vector-`U` comparison uses the largest logged component as a
proxy. Each case also has the descriptive `residual_trend` values for its
requested logged fields; `--trend-window` selects the number of initial and
tail samples used for each median. These ratios do not add convergence
criteria. Even when the residual screen is below tolerance,
`scientific_validation` remains `BLOCKED`: this command does not establish
nonlinear or physical convergence, independent executions, mass balance,
mesh independence, model suitability, or cleanroom performance. It does not
run OpenFOAM.

For the latest actual Foundation v10 nine-case synthetic execution, see the
[run 56 VTK export report](OPENFOAM_V10_RUN_38680418943_VTK_EXPORT.md). It records
all nine final-time VTK hashes and cell counts, the artifact digest, residual
and flux-screen outcomes, and the remaining validation limits. The original
receipt, solver logs, VTK files, and triage JSON are in the linked GitHub
Actions artifact.

## References

- NASA Glenn Research Center, *Examining Spatial (Grid) Convergence*:
  https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html
- NASA CFD verification and validation tutorial:
  https://www.grc.nasa.gov/www/wind/valid/tutorial/tutorial.html
