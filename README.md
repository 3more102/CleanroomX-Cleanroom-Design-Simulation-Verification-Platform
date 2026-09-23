# CleanroomX

CleanroomX is an open engineering platform for **cleanroom design screening, simulation, verification, preliminary HVAC analysis, and room air-balance checking**. The project keeps calculations auditable and requirement-driven rather than hiding them behind a GUI.

## v0.3 engineering core

- Room volume and nominal supply-air ACH calculations.
- Requirement-driven checks for ACH, differential pressure, and airborne particle concentration.
- Multi-room project models and facility-level verification reports.
- Directed room-to-room pressure-cascade verification using project-configured minimum pressure differences.
- Validation for duplicate rooms, unknown cascade references, duplicate links, and impossible directed pressure cycles.
- A transparent well-mixed first-order particle decay/recovery screening model.
- JSON input, command-line workflows, unit tests, and GitHub Actions CI on Python 3.11–3.13.
- Psychrometric room/outdoor air-state calculations.
- Explicit sensible and latent heat-load inputs.
- Makeup-air load and preliminary cooling/heating capacity calculations.
- Governing airflow comparison between cleanroom airflow, makeup air, and sensible-load airflow.
- Optional FFU/filter-unit count from rated airflow and explicit design utilization.
- Explicit return, exhaust, transfer, and leakage airflow accounting.
- Steady-state room air-balance closure with user-entered tolerance.
- Mechanical-surplus, passive-net-outflow, and unmodeled inflow/outflow reporting.

## Important engineering boundary

CleanroomX does **not** claim that ACH, room pressure, a pressure cascade, an airflow surplus, or a simple decay model determines ISO cleanroom classification. ISO 14644-1 classifies air cleanliness by airborne particle concentration. Project, process, safety, and regulatory requirements can add other criteria.

CleanroomX therefore does not embed unofficial ISO classification, ACH, or pressure-cascade limits. Numeric requirements are supplied by the user from the applicable licensed standard, client URS/specification, process design basis, or regulator.

The decay/recovery function is a **screening model**, not CFD. It assumes a well-mixed room and first-order effective removal and does not model particle generation, deposition, leakage, local airflow patterns, or transient HVAC controls.

The HVAC module is also a preliminary engineering model. It does not replace detailed coil selection, weather/load modeling, CFD, commissioning, certification, TAB, or qualified HVAC/cleanroom engineering review.

The room air-balance module is a steady-state volumetric accounting check. A supply/return surplus is **not converted into room pressure**; actual pressure depends on leakage paths, transfer openings, envelope characteristics, controls, and network behavior.

## Install

    python -m pip install -e .[dev]

## Verify one room

    cleanroomx verify examples/basic_room.json

## Verify a multi-room project

    cleanroomx verify-project examples/facility_project.json

The project verifier checks every room and every configured directed pressure-cascade edge. A link such as Process -> Preparation means the observed Process pressure must exceed the observed Preparation pressure by at least the configured minimum delta pressure.

A failing configured requirement returns exit code 2, making both verification commands usable in automated design pipelines.

## Run the screening simulation

    cleanroomx decay --initial 1000000 --ach 30 --minutes 10 --efficiency 0.95
    cleanroomx recovery --initial 1000000 --target 100000 --ach 30 --efficiency 0.95

## Run the HVAC / psychrometric analysis

    cleanroomx-hvac examples/semiconductor_thermal_demo.json

JSON output:

    cleanroomx-hvac examples/semiconductor_thermal_demo.json --format json

Write a Markdown report:

    cleanroomx-hvac examples/semiconductor_thermal_demo.json --output hvac-report.md

## Run the room air-balance example

    cleanroomx-hvac examples/air_balance_demo.json

The air-balance block can define return, exhaust, transfer-in/out, leakage-in/out, and an explicit tolerance. The balance uses the room's governing total supply airflow. Makeup/outdoor air is already a component of total supply and is not added twice.

See docs/THERMAL_MODEL.md, docs/AIR_BALANCE.md, and docs/STANDARDS.md.

## Multi-room pressure-cascade JSON

```json
{
  "name": "Suite",
  "rooms": [
    {
      "name": "Process",
      "length_m": 6.0,
      "width_m": 5.0,
      "height_m": 3.0,
      "supply_airflow_m3_h": 2700.0,
      "observed_pressure_pa": 30.0
    },
    {
      "name": "Ante",
      "length_m": 4.0,
      "width_m": 3.0,
      "height_m": 3.0,
      "supply_airflow_m3_h": 720.0,
      "observed_pressure_pa": 8.0
    }
  ],
  "pressure_cascade": [
    {
      "higher_pressure_room": "Process",
      "lower_pressure_room": "Ante",
      "min_delta_pa": 10.0
    }
  ]
}
```

The numeric limits in the examples are demonstration project inputs, **not quoted ISO limits**.

## Roadmap

Next milestones are inter-room transfer-network consistency checks, expanded filter/fan pressure-drop and sizing models, recovery-test workflows, uncertainty/provenance tracking, richer report generation, and later a desktop/web UI plus CFD adapters.

## Standards references

- ISO 14644-1:2015 — classification of air cleanliness by particle concentration.
- ISO 14644-4:2022 — cleanroom design, construction, and start-up.
- ASHRAE Handbook—Fundamentals — psychrometrics.
- ASHRAE Design Guide for Cleanrooms.

Always use the applicable purchased standard, local regulations, client URS/specification, and qualified engineering judgment for real projects.
