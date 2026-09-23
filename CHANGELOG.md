# Changelog

## v0.5 measurement uncertainty and provenance — 2026-09-23

- Added reusable measurement records with auditable provenance and traceability metadata.
- Added independent-component root-sum-square uncertainty budgets with sensitivity coefficients.
- Added configurable coverage factors, expanded uncertainty, coverage intervals, and relative expanded uncertainty.
- Added explicit upper, lower, and range requirements with pass/fail/indeterminate/not-checked screening states.
- Integrated optional uncertainty, requirement references, and measurement provenance into room ACH, differential-pressure, and particle-concentration verification.
- Added conservative interval propagation for room-to-room pressure-cascade verification; overlapping acceptance thresholds are reported as indeterminate and do not pass overall verification.
- Added JSON loading, Markdown/JSON reporting, a dedicated CLI, example data, tests, and documentation.
- Documented the independence assumption and the boundary that project/regulatory decision rules take precedence.
- Referenced JCGM 100, JCGM 106, and NIST TN 1297 without hard-coding acceptance limits or claiming a universal coverage probability.

## v0.4 recovery qualification — 2026-09-23

- Added measured particle-recovery test records with strict sample validation.
- Added explicit project target concentration and optional maximum recovery-time criteria.
- Added pass/fail/incomplete/not-checked qualification states.
- Added observed recovery windows based on discrete samples without inventing an exact crossing time.
- Added optional traceability metadata for instrument, sample location, occupancy state, and method/protocol reference.
- Added log-linear decay diagnostics, R², fitted target crossing, and estimated effective ACH as screening outputs only.
- Added JSON loading, Markdown/JSON reporting, a dedicated CLI, example data, tests, and documentation.
- Kept ISO/project acceptance thresholds external; no proprietary ISO limits are embedded.

## v0.3 airflow/fan extension — 2026-09-23

- Added per-room supply/return/exhaust/transfer airflow balance.
- Added explicit minimum airflow-surplus verification and margin reporting.
- Added optional filter/FFU pressure-drop input.
- Added preliminary central supply-fan static-pressure, air-power, shaft-power, and electrical-input calculations.
- Added airflow/fan report sections, example inputs, tests, and engineering-scope documentation.
- Kept all limits and pressure-drop values requirement-driven; no ISO class is mapped to airflow surplus or fan sizing.

## v0.2 HVAC extension — 2026-09-23

- Added psychrometric air-state calculations.
- Added explicit sensible and latent room loads.
- Added outdoor/makeup-air load calculations.
- Added preliminary cooling/heating capacity.
- Added cleanroom-vs-makeup-vs-thermal governing airflow selection.
- Added optional FFU/filter-unit sizing.
- Added a separate HVAC CLI, JSON project loader, Markdown reporting, tests, and documentation.
- Preserved the existing particle, room, and pressure-cascade verification architecture.
