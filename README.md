# CleanroomX

CleanroomX is an open engineering platform for **cleanroom design screening, simulation, and verification**. The project keeps engineering logic auditable instead of hiding calculations behind a GUI.

## v0.2 engineering core

- Room volume and nominal supply-air ACH calculations.
- Requirement-driven checks for ACH, differential pressure, and airborne particle concentration.
- Multi-room pressure-cascade verification with directed topology checks.
- Detection of contradictory pressure-direction cycles.
- A transparent well-mixed first-order particle decay/recovery screening model.
- JSON inputs, command-line workflows, unit tests, and GitHub Actions CI on Python 3.11–3.13.

## Important engineering boundary

CleanroomX does **not** claim that ACH, pressure, or a simple decay model determines ISO cleanroom classification. ISO 14644-1 classifies air cleanliness by airborne particle concentration, while ISO 14644-2 addresses monitoring plans related to particle concentration. Project/regulatory requirements can add other criteria. CleanroomX therefore does not embed unofficial ISO classification tables; users configure the limits that apply to their licensed standard, process, client specification, or regulator.

Pressure-cascade verification only checks the user-configured zone relationships and observed pressure values. It does not determine door leakage, airflow balance, containment performance, or regulatory compliance by itself.

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

## Verify a multi-room pressure cascade

```bash
cleanroomx verify-cascade examples/pressure_cascade.json
```

The cascade input expresses only project-defined pressure relationships:

```json
{
  "name": "Example cleanroom pressure cascade",
  "zones": [
    {"name": "Core", "observed_pressure_pa": 30.0},
    {"name": "Gowning", "observed_pressure_pa": 18.0},
    {"name": "Corridor", "observed_pressure_pa": 5.0}
  ],
  "requirements": [
    {"high_zone": "Core", "low_zone": "Gowning", "min_delta_pa": 10.0},
    {"high_zone": "Gowning", "low_zone": "Corridor", "min_delta_pa": 10.0}
  ]
}
```

These values are demonstration project inputs, not quoted standard limits. CleanroomX also reports a topology failure if the direction rules form a cycle such as `A -> B -> A`, because strictly positive pressure differences cannot satisfy that graph consistently.

## Run the screening simulation

```bash
cleanroomx decay --initial 1000000 --ach 30 --minutes 10 --efficiency 0.95
cleanroomx recovery --initial 1000000 --target 100000 --ach 30 --efficiency 0.95
```

## Single-room input format

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

Next milestones are HEPA/filter and fan sizing inputs, heat-load and psychrometric calculations, recovery-test workflows, uncertainty/provenance tracking, report generation, and later a desktop/web UI plus CFD adapters.

## Standards references

- ISO 14644-1:2015 — classification of air cleanliness by particle concentration.
- ISO 14644-2:2015 — monitoring to provide evidence of cleanroom performance related to air cleanliness by particle concentration.

Always use the applicable purchased standard, local regulations, client URS/specification, and qualified engineering judgment for real projects.
