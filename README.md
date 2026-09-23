# CleanroomX

CleanroomX is an open engineering platform for **cleanroom design screening, simulation, and verification**. The first milestone provides a small, auditable Python core rather than hiding calculations behind a GUI.

## v0.1 foundation

- Room volume and nominal supply-air ACH calculations.
- Requirement-driven checks for ACH, differential pressure, and airborne particle concentration.
- A transparent well-mixed first-order particle decay/recovery screening model.
- JSON input and a command-line interface.
- Unit tests and GitHub Actions CI on Python 3.11–3.13.

## Important engineering boundary

CleanroomX does **not** claim that ACH, pressure, or a simple decay model determines ISO cleanroom classification. ISO 14644-1 classifies air cleanliness by airborne particle concentration, while ISO 14644-2 addresses monitoring plans related to particle concentration. Project/regulatory requirements can add other criteria. CleanroomX therefore does not embed unofficial ISO classification tables; users configure the limits that apply to their licensed standard, process, client specification, or regulator.

The decay/recovery function is a **screening model**, not CFD. It assumes a well-mixed room and first-order effective removal and does not model particle generation, deposition, leakage, local airflow patterns, or transient HVAC controls.

## Install

```bash
python -m pip install -e .[dev]
```

## Verify an example room

```bash
cleanroomx verify examples/basic_room.json
```

A failing configured requirement returns exit code `2`, making the verifier usable in automated design pipelines.

## Run the screening simulation

```bash
cleanroomx decay --initial 1000000 --ach 30 --minutes 10 --efficiency 0.95
cleanroomx recovery --initial 1000000 --target 100000 --ach 30 --efficiency 0.95
```

## Input format

```json
{
  "name": "Example cleanroom",
  "length_m": 6.0,
  "width_m": 4.0,
  "height_m": 3.0,
  "supply_airflow_m3_h": 1800.0,
  "min_ach": 20.0,
  "min_pressure_pa": 10.0,
  "observed_pressure_pa": 14.0,
  "particle_requirements": [
    {
      "size_um": 0.5,
      "max_concentration_per_m3": 400000.0,
      "observed_concentration_per_m3": 120000.0
    }
  ]
}
```

The numeric limits in this example are demonstration project inputs, **not quoted ISO limits**.

## Roadmap

Next milestones are a multi-room pressure-cascade graph, HEPA/filter and fan sizing inputs, heat-load and psychrometric calculations, recovery-test workflows, uncertainty/provenance tracking, report generation, and later a desktop/web UI plus CFD adapters.

## Standards references

- ISO 14644-1:2015 — classification of air cleanliness by particle concentration.
- ISO 14644-2:2015 — monitoring to provide evidence of cleanroom performance related to air cleanliness by particle concentration.

Always use the applicable purchased standard, local regulations, client URS/specification, and qualified engineering judgment for real projects.
