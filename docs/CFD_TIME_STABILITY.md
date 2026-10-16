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
linear-trend slope and R². It also compares every consecutive pair of same-mesh
cell fields with a volume-weighted symmetric relative L2 change. Velocity
comparisons use all three components of `U`; contaminant comparisons use the
selected scalar array. This catches spatial redistribution that can leave a
volume-weighted mean unchanged.

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
- `max_relative_field_change` is an explicit project screen from 0 to 2.
  Without a project value, temporal cell-field changes remain descriptive and
  engineering review remains blocked.

Run the analysis and save its report:

    cleanroomx-cfd-pipeline time-audit cfd_time_study.json \
      --output cfd_time_analysis.json \
      --plot cfd_time_analysis.png

`--plot` is optional and writes a PNG from the same imported VTK summaries. It
shows the volume-weighted mean and p05–p95 band for each selected output, plus
the consecutive same-mesh full-field change and any configured project limit.
The x-axis uses the original OpenFOAM solver-time labels and explicitly does
not label them as seconds. The plot is diagnostic and retains the report's
blocked scientific-validation status. Existing PNG files are never replaced.

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

For each consecutive pair, the symmetric relative L2 change is the
volume-weighted RMS of the cell-field difference divided by the mean of the two
volume-weighted field RMS magnitudes. It is dimensionless, ranges from 0 to 2,
and is compared only with the explicit `max_relative_field_change` supplied in
the study. The absolute RMS change is also reported in the selected quantity's
units. Mesh geometry and cell ordering must match exactly before a pair is
compared; mismatched pairs are reported as non-comparable and block review.

Output status remains `DIAGNOSTIC_ONLY` and `scientific_validation` remains
`BLOCKED`, even when all software and project-selected screens are satisfied.
The report does not establish steady-state convergence, physical-time
stationarity, mesh independence, model correctness, measurement agreement,
cleanroom performance, or certification. Synthetic VTK fixtures verify the
software calculations only; actual engineering conclusions require reviewed
physical inputs and independently supported evidence.


## Current Foundation v10 integration evidence

OpenFOAM Foundation v10 run [#160](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38944498458) completed the nine generated synthetic cases and all 36 command stages. Each case produced three synchronized VTK snapshots at solver-time labels `50`, `100`, and `150`, for 27 snapshots total. The run artifact [#12064319325](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38944498458/artifacts/12064319325) has SHA-256 `c99c6e69976802f331d5150a8b6ba8a8e82d4c99ab65bc9613ad541f8f058ace`; the downloaded archive digest matched this value.

This run confirms OpenFOAM execution and result synchronization. It did not run `time-audit` against those VTK files. The cases remain `executed_requires_convergence_review`; no project-defined temporal range or room-volume criterion was supplied, and scientific validation remains `BLOCKED`. The three available snapshots meet the sample-count minimum but do not make the temporal or engineering screens pass.
