# Changelog

## v0.3 air-balance extension — 2026-09-23

- Added explicit return, exhaust, transfer, and leakage airflow inputs per HVAC room.
- Added steady-state room air-balance closure with user-defined tolerance.
- Added mechanical-surplus and passive-net-outflow reporting.
- Added explicit unmodeled inflow/outflow requirements when a balance does not close.
- Integrated air-balance results into HVAC JSON analysis and Markdown reports.
- Added an air-balance example, engineering documentation, and regression tests.
- Kept room pressure verification separate; airflow surplus is not converted into pressure.

## v0.2 HVAC extension — 2026-09-23

- Added psychrometric air-state calculations.
- Added explicit sensible and latent room loads.
- Added outdoor/makeup-air load calculations.
- Added preliminary cooling/heating capacity.
- Added cleanroom-vs-makeup-vs-thermal governing airflow selection.
- Added optional FFU/filter-unit sizing.
- Added a separate HVAC CLI, JSON project loader, Markdown reporting, tests, and documentation.
- Preserved the existing particle, room, and pressure-cascade verification architecture.
