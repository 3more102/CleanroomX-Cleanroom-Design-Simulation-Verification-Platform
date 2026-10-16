# Selected-time CFD field analysis

`cleanroomx-cfd-pipeline time-audit` summarizes volume-weighted VTK fields at
multiple selected outputs from **one solver run on one fixed mesh**. It adds a
temporal quantity-of-interest screen ahead of grid-convergence review:
spatial GCI is difficult to interpret when the selected quantity is still
changing across the solver outputs.

The tool accepts 2–100 explicitly named `.vtk` or `.vtu` samples. A project
must select at least three samples for a range screen. It checks strict time
label ordering, input-path confinement, VTK readability, same-mesh geometry,
volume totals, and a separately configured solver-log residual screen. For
each sample it reports the selected quantity's volume-weighted mean,
population standard deviation, 5th/50th/95th weighted percentiles, minimum,
maximum, cell count, volume, and SHA-256 evidence. Across samples it reports
the mean, minimum, maximum, absolute and relative range, endpoint change, and
linear-trend slope and R².

Inputs are bounded to the VTK reader's existing 256 MiB per-file limit and a
2 GiB aggregate VTK limit per study.

## Use

Create a strict-JSON study file next to the selected VTK datasets and solver
log. Set these fields from the actual case and project:

- `configuration`, `solver`, and `run_id` identify the run.
- `conditions_sha256` is an analyst-supplied comparability assertion. It is
  reported verbatim and does not independently reconstruct solver settings,
  geometry, or boundary conditions.
- `quantity` is `velocity_mean_m_s` or `contaminant_mean`. Velocity must use
  `m/s`; the contaminant unit and array name are supplied by the project.
- `room_volume_m3` is the expected sampled volume. The optional
  `max_relative_volume_error` is a project input. Without it, the volume
  deviation is still reported but the review status remains blocked.
- `samples` lists distinct VTK paths and strictly increasing numeric
  `solver_time_name` labels. These labels are preserved as OpenFOAM directory
  names; CleanroomX does not infer that they are seconds. In steady SIMPLE
  runs, a time label can represent iteration progress rather than physical
  time.
- `log_audit` uses the project's residual fields, sample window, and numeric
  limits. Those limits are not supplied or inferred by CleanroomX.
- `minimum_samples` must be at least three. `max_relative_range` is optional;
  until the project supplies it, the range remains descriptive and the screen
  status is `NO_PROJECT_RANGE_CRITERION`.

Run the analysis and save its report:

    cleanroomx-cfd-pipeline time-audit cfd_time_study.json \
      --output cfd_time_analysis.json \
      --plot-output cfd_time_analysis.svg

`--plot-output` is optional. It writes a self-contained SVG showing the
volume-weighted mean at each selected output, a shaded within-snapshot spatial
p05–p95 band, and a descriptive linear trend. The x-axis retains the supplied
OpenFOAM time-directory labels and explicitly does not treat them as seconds.
The band describes spatial field variation; it is not an uncertainty interval.
SVG and JSON destinations are atomically written and protected from the study
specification, selected VTK files, solver log, and each other.

The CLI returns 0 only when the configured temporal and volume screens,
same-mesh check, and solver-log screen are all ready for engineering review.
Missing project thresholds keep review blocked. A nonzero result still
includes computed diagnostics when the inputs were readable, so reviewers can
see why the screen is blocked.

## Interpretation boundary

The relative range is `(maximum quantity mean - minimum quantity mean) /
mean(abs(quantity mean))`; it is compared only with the explicit
`max_relative_range` supplied in the study. The fitted slope is expressed per
numeric solver-time-label unit, not per second unless the project separately
establishes that meaning. A linear fit summarizes the selected points and is
not a convergence model.

Output status remains `DIAGNOSTIC_ONLY` and `scientific_validation` remains
`BLOCKED`, even when all software and project-selected screens are satisfied.
The report does not establish steady-state convergence, physical-time
stationarity, mesh independence, model correctness, measurement agreement,
cleanroom performance, or certification. Synthetic VTK fixtures verify the
software calculations only; actual engineering conclusions require reviewed
physical inputs and independently supported evidence.
