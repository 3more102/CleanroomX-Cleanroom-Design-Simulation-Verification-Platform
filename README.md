# CleanroomX

CleanroomX is an open engineering platform for **cleanroom design screening, airflow balance, simulation, verification, and preliminary HVAC analysis**. The project keeps calculations auditable and requirement-driven rather than hiding them behind a GUI.

## v0.3 engineering core

- Room volume and nominal supply-air ACH calculations.
- Requirement-driven checks for ACH, differential pressure, and airborne particle concentration.
- Multi-room project models and facility-level pressure-cascade verification.
- Validation for duplicate rooms, unknown cascade references, duplicate links, and impossible directed pressure cycles.
- A transparent well-mixed first-order particle decay/recovery screening model.
- Psychrometric room/outdoor air-state calculations.
- Explicit sensible and latent heat-load inputs.
- Makeup-air load and preliminary cooling/heating capacity calculations.
- Governing airflow comparison between cleanroom airflow, makeup air, and sensible-load airflow.
- Optional FFU/filter-unit count from rated airflow and explicit design utilization.
- Supply/return/exhaust room airflow-balance calculations.
- Directed room-to-room transfer-air tracking.
- Facility airflow-conservation checks.
- Configurable minimum/maximum net-offset verification.
- JSON input, Markdown/JSON reports, CLI workflows, tests, and GitHub Actions CI on Python 3.11–3.13.

## Important engineering boundary

CleanroomX does **not** claim that ACH, room pressure, airflow offset, a pressure cascade, or a simple decay model determines ISO cleanroom classification. ISO 14644-1 classifies air cleanliness by airborne particle concentration. Project, process, safety, and regulatory requirements can add other criteria.

CleanroomX does not embed unofficial ISO classification, ACH, pressure-cascade, or airflow-offset limits. Numeric requirements are supplied by the user from the applicable licensed standard, client URS/specification, process design basis, or regulator.

The decay/recovery function is a **screening model**, not CFD. It assumes a well-mixed room and first-order effective removal and does not model particle generation, deposition, leakage, local airflow patterns, or transient HVAC controls.

The HVAC and airflow-balance modules are preliminary engineering tools. Airflow offset is reported as a pressurization tendency and is not converted into differential pressure; actual pressure depends on envelope leakage, openings, adjacent spaces, controls, and commissioning.

## Install

    python -m pip install -e .[dev]

## Verify one room

    cleanroomx verify examples/basic_room.json

## Verify a multi-room pressure cascade

    cleanroomx verify-project examples/facility_project.json

A failing configured verification requirement returns exit code 2.

## Run the particle screening simulation

    cleanroomx decay --initial 1000000 --ach 30 --minutes 10 --efficiency 0.95
    cleanroomx recovery --initial 1000000 --target 100000 --ach 30 --efficiency 0.95

## Run the HVAC / psychrometric analysis

    cleanroomx-hvac examples/semiconductor_thermal_demo.json

JSON output:

    cleanroomx-hvac examples/semiconductor_thermal_demo.json --format json

Write a Markdown report:

    cleanroomx-hvac examples/semiconductor_thermal_demo.json --output hvac-report.md

See docs/THERMAL_MODEL.md and docs/STANDARDS.md.

## Run the airflow-balance analysis

    cleanroomx-balance examples/airflow_balance_demo.json

JSON output:

    cleanroomx-balance examples/airflow_balance_demo.json --format json

Write a Markdown report:

    cleanroomx-balance examples/airflow_balance_demo.json --output airflow-balance.md

The balance engine evaluates each room using supply + transfer-in versus return + exhaust + transfer-out. Internal room-to-room transfers cancel at facility level, allowing the tool to expose conservation errors and verify user-configured room offset bounds.

See docs/AIRFLOW_BALANCE.md.

## Roadmap

Next milestones are expanded filter/fan and static-pressure sizing, recovery-test qualification workflows, uncertainty/provenance tracking, richer engineering reports, and later a desktop/web UI plus CFD adapters.

## Standards and engineering references

- ISO 14644-1:2015 — classification of air cleanliness by particle concentration.
- ISO 14644-4:2022 — cleanroom design, construction, and start-up.
- ASHRAE Handbook—Fundamentals — psychrometrics.
- ASHRAE Handbook — Clean Spaces — cleanroom pressurization and airflow-offset concepts.

Always use the applicable purchased standard, local regulations, client URS/specification, and qualified engineering judgment for real projects.
