# Changelog

## v0.4 recovery-test workflow — 2026-09-23

- Added measured particle-concentration recovery-test datasets with strict time/sample validation.
- Added first target-crossing detection with log-concentration interpolation.
- Added log-linear concentration-decay fitting, effective removal rate, half-life, and R² reporting.
- Added optional project maximum-recovery-time acceptance checks with exit code 2 on failure.
- Added optional comparison against the existing ACH/removal-efficiency screening model.
- Added JSON and Markdown recovery-test reporting, CLI support, an example dataset, tests, and documentation.
- Kept acceptance criteria and test-method requirements explicit; fitted results are not presented as certification.

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
