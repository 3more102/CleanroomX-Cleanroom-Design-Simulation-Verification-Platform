# CleanroomX

CleanroomX is an open engineering platform for **cleanroom design screening, simulation, verification, preliminary HVAC analysis, and measured recovery-test analysis**. The project keeps calculations auditable and requirement-driven rather than hiding them behind a GUI.

## v0.4 engineering core

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
- Per-room supply/return/exhaust/transfer airflow balance and minimum-surplus verification.
- Optional terminal-filter pressure drop plus preliminary supply-fan static-pressure and electrical-power sizing.
- Measured recovery-test time-series analysis with first target crossing, log-linear fit, effective removal rate, half-life, and R².
- Optional configured maximum recovery-time check and comparison with the ACH screening model.

## Important engineering boundary

CleanroomX does **not** claim that ACH, room pressure, a pressure cascade, airflow surplus, a simple decay fit, or recovery-test regression determines ISO cleanroom classification. ISO 14644-1 classifies air cleanliness by airborne particle concentration. Project, process, safety, test-method, and regulatory requirements can add other criteria.

CleanroomX therefore does not embed unofficial ISO classification, ACH, pressure-cascade, airflow-surplus, filter-pressure-drop, fan-sizing, or recovery-time acceptance limits. Numeric requirements are supplied by the user from the applicable licensed standard, client URS/specification, validated test method, manufacturer data, or regulator.

The decay/recovery screening function is **not CFD**. The measured recovery-test workflow is descriptive analysis of supplied observations; it does not define challenge generation, sample locations, instrument requirements, background correction, or certification procedure.

The HVAC module is also a preliminary engineering model. It does not replace detailed coil selection, weather/load modeling, duct design, fan-curve selection, CFD, commissioning, certification, or qualified HVAC/cleanroom engineering review.

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

## Analyze a measured recovery test

JSON output:

    cleanroomx recovery-test examples/recovery_test_demo.json

Markdown output:

    cleanroomx recovery-test examples/recovery_test_demo.json --format markdown

Write a Markdown report:

    cleanroomx recovery-test examples/recovery_test_demo.json --format markdown --output recovery-report.md

If the input configures a maximum recovery time and the measured target crossing is later than that limit, or is not reached in the supplied samples, the command returns exit code 2.

See docs/RECOVERY_TEST.md for the equations, interpolation method, fit outputs, and engineering boundaries.

## Run the HVAC / psychrometric analysis

    cleanroomx-hvac examples/semiconductor_thermal_demo.json

JSON output:

    cleanroomx-hvac examples/semiconductor_thermal_demo.json --format json

Write a Markdown report:

    cleanroomx-hvac examples/semiconductor_thermal_demo.json --output hvac-report.md

The HVAC input keeps the independently selected cleanroom airflow separate from thermal sizing. It can also include room air-balance data and a preliminary supply-fan model. See docs/THERMAL_MODEL.md, docs/AIRFLOW_FAN_MODEL.md, and docs/STANDARDS.md.

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

Next milestones are uncertainty/provenance tracking, richer report generation, duct/network pressure-loss modeling, measured-data import adapters, and later a desktop/web UI plus CFD adapters.

## Standards references

- ISO 14644-1:2015 — classification of air cleanliness by particle concentration.
- ISO 14644-4:2022 — cleanroom design, construction, and start-up.
- ASHRAE Handbook—Fundamentals — psychrometrics.
- ASHRAE Design Guide for Cleanrooms.

Always use the applicable purchased standard, local regulations, client URS/specification, validated test methods, manufacturer data, and qualified engineering judgment for real projects.
