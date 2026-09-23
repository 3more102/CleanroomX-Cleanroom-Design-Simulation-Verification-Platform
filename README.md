# CleanroomX

CleanroomX is an open engineering platform for **cleanroom design screening, simulation, verification, measurement uncertainty, recovery qualification, and preliminary HVAC analysis**. The project keeps calculations auditable and requirement-driven rather than hiding them behind a GUI.

## v0.5 engineering core

- Room volume and nominal supply-air ACH calculations.
- Requirement-driven checks for ACH, differential pressure, and airborne particle concentration.
- Multi-room project models and facility-level verification reports.
- Directed room-to-room pressure-cascade verification using project-configured minimum pressure differences.
- Validation for duplicate rooms, unknown cascade references, duplicate links, and impossible directed pressure cycles.
- A transparent well-mixed first-order particle decay/recovery screening model.
- Psychrometric room/outdoor air-state calculations.
- Explicit sensible and latent heat-load inputs.
- Makeup-air load and preliminary cooling/heating capacity calculations.
- Governing airflow comparison between cleanroom airflow, makeup air, and sensible-load airflow.
- Optional FFU/filter-unit count from rated airflow and explicit design utilization.
- Per-room supply/return/exhaust/transfer airflow balance and minimum-surplus verification.
- Optional terminal-filter pressure drop plus preliminary supply-fan static-pressure and electrical-power sizing.
- Measured particle-recovery qualification records with project-configured target and maximum recovery time.
- Recovery traceability metadata plus pass/fail/incomplete/not-checked status.
- Generic measurement uncertainty budgets with provenance, expanded intervals, and uncertainty-aware screening decisions.
- Optional absolute uncertainty and requirement provenance integrated into ACH, room-pressure, particle-concentration, and pressure-cascade verification; threshold overlaps return `indeterminate` rather than a false PASS/FAIL.
- Log-linear decay diagnostics and estimated effective ACH as screening outputs only.
- JSON input, Markdown/JSON reports, CLI workflows, tests, and GitHub Actions CI on Python 3.11–3.13.

## Important engineering boundary

CleanroomX does **not** claim that ACH, room pressure, a pressure cascade, airflow surplus, a fitted recovery model, or a simple decay model determines ISO cleanroom classification. ISO 14644-1 classifies air cleanliness by airborne particle concentration. ISO 14644-3 provides cleanroom test methods. Project, process, safety, and regulatory requirements can add other criteria.

CleanroomX therefore does not embed unofficial ISO classification, ACH, pressure-cascade, airflow-surplus, filter-pressure-drop, fan-sizing, particle-target, or recovery-time limits. Numeric requirements are supplied by the user from the applicable licensed standard, client URS/specification, qualification protocol, process design basis, manufacturer data, or regulator.

The decay/recovery function is a **screening model**, not CFD. It assumes a well-mixed room and first-order effective removal and does not model particle generation, deposition, leakage, local airflow patterns, or transient HVAC controls.

The HVAC module is also a preliminary engineering model. It does not replace detailed coil selection, weather/load modeling, duct design, fan-curve selection, CFD, commissioning, certification, or qualified HVAC/cleanroom engineering review.

## Install

    python -m pip install -e .[dev]

## Verify one room

    cleanroomx verify examples/basic_room.json

## Verify a multi-room project

    cleanroomx verify-project examples/facility_project.json

A failed or indeterminate configured verification requirement returns exit code 2.

## Run the particle screening simulation

    cleanroomx decay --initial 1000000 --ach 30 --minutes 10 --efficiency 0.95
    cleanroomx recovery --initial 1000000 --target 100000 --ach 30 --efficiency 0.95

## Run the HVAC / psychrometric analysis

    cleanroomx-hvac examples/semiconductor_thermal_demo.json

JSON output:

    cleanroomx-hvac examples/semiconductor_thermal_demo.json --format json

Write a Markdown report:

    cleanroomx-hvac examples/semiconductor_thermal_demo.json --output hvac-report.md

The HVAC input keeps the independently selected cleanroom airflow separate from thermal sizing. It can also include room air-balance data and a preliminary supply-fan model. See docs/THERMAL_MODEL.md, docs/AIRFLOW_FAN_MODEL.md, and docs/STANDARDS.md.

## Analyze a measured particle-recovery test

    cleanroomx-recovery-test examples/recovery_test_demo.json

JSON output:

    cleanroomx-recovery-test examples/recovery_test_demo.json --format json

Write a Markdown report:

    cleanroomx-recovery-test examples/recovery_test_demo.json --output recovery-report.md

The recovery workflow uses measured time/concentration samples directly. It records the first measured sample at or below the configured target, the measurement interval in which recovery occurred, optional traceability fields, and an optional maximum-time criterion. The log-linear fit is diagnostic only and does not replace the measured qualification result.

See docs/RECOVERY_TEST.md.

## Analyze a measurement uncertainty budget

    cleanroomx-measurement examples/measurement_uncertainty_demo.json

JSON output:

    cleanroomx-measurement examples/measurement_uncertainty_demo.json --format json

Write a Markdown report:

    cleanroomx-measurement examples/measurement_uncertainty_demo.json --output measurement-report.md

The v0.5 measurement workflow combines independent standard-uncertainty components by root-sum-square, applies the configured coverage factor, preserves instrument/calibration/procedure provenance, and reports pass/fail/indeterminate/not-checked using an explicit interval screening rule. It does not infer a universal coverage probability or replace a project/regulatory decision rule.

See docs/MEASUREMENT_UNCERTAINTY.md and docs/UNCERTAINTY_PROVENANCE.md.

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

Next milestones are richer engineering reports, duct/network pressure-loss modeling, deeper uncertainty integration into qualification/HVAC workflows, and later a desktop/web UI plus CFD adapters.

## Standards and metrology references

- ISO 14644-1:2015 — classification of air cleanliness by particle concentration.
- ISO 14644-3:2019 — cleanroom and clean-zone test methods.
- ISO 14644-4:2022 — cleanroom design, construction, and start-up.
- ASHRAE Handbook—Fundamentals — psychrometrics.
- ASHRAE Design Guide for Cleanrooms.
- JCGM 100:2008 — Guide to the Expression of Uncertainty in Measurement.
- JCGM 106:2012 — role of measurement uncertainty in conformity assessment.
- NIST Technical Note 1297 — guidance for evaluating and expressing measurement uncertainty.

Always use the applicable purchased standard, local regulations, client URS/specification, qualification protocol, manufacturer data, and qualified engineering judgment for real projects.
