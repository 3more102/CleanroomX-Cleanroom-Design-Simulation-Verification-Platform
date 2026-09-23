# Changelog

## v0.3 airflow-balance extension — 2026-09-23

- Added room supply/return/exhaust airflow-balance calculations.
- Added directed room-to-room transfer-air modeling.
- Added facility-level airflow conservation checks.
- Added configurable minimum/maximum room net-offset requirements.
- Added positive/negative/neutral pressurization-tendency reporting without converting offset into pressure.
- Added JSON loading, Markdown/JSON reporting, a `cleanroomx-balance` CLI, tests, example data, and engineering documentation.
- Kept regulatory and client limits as explicit project inputs rather than hard-coded defaults.

## v0.2 HVAC extension — 2026-09-23

- Added psychrometric air-state calculations.
- Added explicit sensible and latent room loads.
- Added outdoor/makeup-air load calculations.
- Added preliminary cooling/heating capacity.
- Added cleanroom-vs-makeup-vs-thermal governing airflow selection.
- Added optional FFU/filter-unit sizing.
- Added a separate HVAC CLI, JSON project loader, Markdown reporting, tests, and documentation.
- Preserved the existing particle, room, and pressure-cascade verification architecture.
