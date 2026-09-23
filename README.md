# CleanroomX

CleanroomX is an open engineering platform for **cleanroom design screening, simulation, and verification**. The project keeps calculations auditable and requirement-driven rather than hiding them behind a GUI.

## v0.2 engineering core

- Room volume and nominal supply-air ACH calculations.
- Requirement-driven checks for ACH, differential pressure, and airborne particle concentration.
- Multi-room project models and facility-level verification reports.
- Directed room-to-room pressure-cascade verification using project-configured minimum pressure differences.
- Validation for duplicate rooms, unknown cascade references, duplicate links, and impossible directed pressure cycles.
- A transparent well-mixed first-order particle decay/recovery screening model.
- JSON input, command-line workflows, unit tests, and GitHub Actions CI on Python 3.11–3.13.

## Important engineering boundary

CleanroomX does **not** claim that ACH, room pressure, a pressure cascade, or a simple decay model determines ISO cleanroom classification. ISO 14644-1 classifies air cleanliness by airborne particle concentration, while ISO 14644-2 addresses monitoring plans related to particle concentration. Project, process, safety, and regulatory requirements can add other criteria.

CleanroomX therefore does not embed unofficial ISO classification or pressure-cascade limits. Numeric requirements are supplied by the user from the applicable licensed standard, client URS/specification, process design basis, or regulator.

The decay/recovery function is a **screening model**, not CFD. It assumes a well-mixed room and first-order effective removal and does not model particle generation, deposition, leakage, local airflow patterns, or transient HVAC controls.

## Install

```bash
python -m pip install -e .[dev]
```

## Verify one room

```bash
cleanroomx verify examples/basic_room.json
```

## Verify a multi-room project

```bash
cleanroomx verify-project examples/facility_project.json
```

The project verifier checks every room and every configured directed pressure-cascade edge. A link such as `Process -> Preparation` means the observed Process pressure must exceed the observed Preparation pressure by at least `min_delta_pa`.

A failing configured requirement returns exit code `2`, making both verification commands usable in automated design pipelines.

## Run the screening simulation

```bash
cleanroomx decay --initial 1000000 --ach 30 --minutes 10 --efficiency 0.95
cleanroomx recovery --initial 1000000 --target 100000 --ach 30 --efficiency 0.95
```

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

Next milestones are supply/return/exhaust air-balance modeling, HEPA/filter and fan sizing inputs, heat-load and psychrometric calculations, recovery-test workflows, uncertainty/provenance tracking, report generation, and later a desktop/web UI plus CFD adapters.

## Standards references

- ISO 14644-1:2015 — classification of air cleanliness by particle concentration.
- ISO 14644-2:2015 — monitoring to provide evidence of cleanroom performance related to air cleanliness by particle concentration.

Always use the applicable purchased standard, local regulations, client URS/specification, and qualified engineering judgment for real projects.
