# CleanroomX

CleanroomX is an open engineering platform for **cleanroom design screening, simulation, verification, recovery qualification, uncertainty/provenance tracking, and preliminary HVAC analysis**. The project keeps calculations auditable and requirement-driven rather than hiding them behind a GUI.

## v0.14 engineering core

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
- Path-based duct pressure-loss analysis using Darcy-Weisbach friction plus explicit local loss coefficients.
- Circular and rectangular duct geometry with hydraulic-diameter reporting.
- Critical-path selection across user-defined duct paths and direct integration into fan duty.
- Directed supply-tree branch-flow solving from explicit terminal demands with continuity residuals and terminal critical-path analysis.
- Passive parallel-path airflow solving for simple common-pressure-node networks using explicit fixed resistances.
- Fan/system operating-point solving from supplied fan performance points and an explicit fixed-plus-quadratic system curve, without extrapolation.
- HVAC fan-curve design-duty verification at the required governing airflow and computed/entered static pressure, with bounded interpolation and no extrapolation.
- Fan/duct-network operating-point integration that derives a critical quadratic system resistance from explicit duct geometry, loss inputs, and fixed reference airflow fractions.
- Manifest-driven integrated engineering dossiers with SHA-256 source fingerprints across verification, HVAC/fan-duty screening, recovery, uncertainty, thermal-uncertainty, and standalone fan/system studies.
- Optional cross-module verification/HVAC airflow reconciliation with explicit project-supplied tolerance, exact-name or explicit room mapping, and unmapped-room completeness guards.
- Measured particle-recovery qualification records with project-configured target and maximum recovery time.
- Recovery traceability metadata plus pass/fail/incomplete/not-checked status.
- Log-linear decay diagnostics and estimated effective ACH as screening outputs only.
- Conservative interval propagation for uncertain room dimensions and supply airflow.
- Provenance records for engineering input source, reference, revision/date, and uncertainty basis.
- Robust minimum-ACH decisions with pass/fail/indeterminate/not-checked status.
- Conservative uncertainty-aware minimum/maximum qualification checks for measured quantities such as pressure and particle concentration.
- Worst-case interval propagation for room-to-room pressure cascades, with `indeterminate` when an acceptance threshold is overlapped.
- Deterministic thermal/HVAC uncertainty intervals for explicit loads, airflow, supply-air temperature, and equipment-capacity screening.
- JSON input, Markdown/JSON reports, CLI workflows, tests, and GitHub Actions CI on Python 3.11–3.13.

## Important engineering boundary

CleanroomX does **not** claim that ACH, room pressure, a pressure cascade, airflow surplus, a fitted recovery model, or a simple decay model determines ISO cleanroom classification. ISO 14644-1 classifies air cleanliness by airborne particle concentration. ISO 14644-3 provides cleanroom test methods. Project, process, safety, and regulatory requirements can add other criteria.

CleanroomX therefore does not embed unofficial ISO classification, ACH, pressure-cascade, airflow-surplus, filter-pressure-drop, duct-friction, fitting-loss, fan-sizing, particle-target, or recovery-time limits. Numeric requirements are supplied by the user from the applicable licensed standard, client URS/specification, qualification protocol, process design basis, manufacturer data, or regulator.

The decay/recovery function is a **screening model**, not CFD. It assumes a well-mixed room and first-order effective removal and does not model particle generation, deposition, leakage, local airflow patterns, or transient HVAC controls.

The HVAC module is also a preliminary engineering model. The v0.8 branch-flow solver propagates fixed terminal demands through a directed tree by mass continuity, while the v0.9 standalone parallel-flow solver distributes a specified total flow across simple paths sharing the same pressure nodes under fixed R·Q² resistance assumptions. The v0.11 standalone fan-curve solver finds an operating point only inside user-supplied fan data against an explicit fixed-plus-quadratic system curve. The v0.12 HVAC fan-curve duty check instead tests the required HVAC airflow/static-pressure duty against bounded interpolation of supplied fan data; it does not infer an HVAC system curve or extrapolate fan performance. The v0.14 fan/duct-network workflow complements that design-duty check by deriving a fixed-ratio quadratic system curve from the path-based duct model and solving its bounded intersection with the supplied fan curve. These are bounded models rather than a general nonlinear duct-network/control solver; CleanroomX does not infer arbitrary looped-network flows, variable friction factors, damper positions, leakage, system effect, acoustics, controls, stall/surge limits, or commissioning acceptance. It does not replace detailed coil selection, weather/load modeling, duct design, manufacturer fan selection, CFD, commissioning, certification, or qualified HVAC/cleanroom engineering review.

The uncertainty workflows use deterministic worst-case input intervals. They are not statistical measurement-uncertainty budgets, do not invent tolerances or acceptance limits, and do not replace calibration records, project qualification procedures, or project/regulatory conformity decision rules. The v0.10 thermal uncertainty workflow holds room/outdoor psychrometric states fixed and does not replace hourly load simulation or equipment selection.

## Install

    python -m pip install -e .[dev]

## Verify one room

    cleanroomx verify examples/basic_room.json

## Verify a multi-room project

    cleanroomx verify-project examples/facility_project.json

A failing configured verification requirement returns exit code 2.

## Run the particle screening simulation

    cleanroomx decay --initial 1000000 --ach 30 --minutes 10 --efficiency 0.95
    cleanroomx recovery --initial 1000000 --target 100000 --ach 30 --efficiency 0.95

## Run the HVAC / psychrometric analysis

    cleanroomx-hvac examples/semiconductor_thermal_demo.json

Duct critical-path demo:

    cleanroomx-hvac examples/duct_network_demo.json

Branch-flow supply-tree demo:

    cleanroomx-hvac examples/branch_flow_network_demo.json

JSON output:

    cleanroomx-hvac examples/duct_network_demo.json --format json

Write a Markdown report:

    cleanroomx-hvac examples/duct_network_demo.json --output hvac-report.md

The HVAC input keeps the independently selected cleanroom airflow separate from thermal sizing. It can also include room air-balance data, a preliminary supply-fan model, an optional supplied fan curve for design-duty verification, and either the path-based duct model or the branch-flow supply-tree model. See docs/THERMAL_MODEL.md, docs/AIRFLOW_FAN_MODEL.md, docs/DUCT_NETWORK_MODEL.md, docs/BRANCH_FLOW_NETWORK.md, and docs/STANDARDS.md.

## Solve passive parallel duct flow

    cleanroomx-duct-flow examples/parallel_flow_demo.json

JSON output:

    cleanroomx-duct-flow examples/parallel_flow_demo.json --format json

Write a Markdown report:

    cleanroomx-duct-flow examples/parallel_flow_demo.json --output parallel-flow-report.md

The v0.9 solver applies only to passive duct paths that share the same upstream and downstream pressure nodes. It solves the flow split from explicit fixed path resistances and reports both mass-balance and equal-pressure residuals. See docs/PARALLEL_FLOW_SOLVER.md.

## Solve a fan/system operating point

    cleanroomx-fan-curve examples/fan_operating_point_demo.json

JSON output:

    cleanroomx-fan-curve examples/fan_operating_point_demo.json --format json

Write a Markdown report:

    cleanroomx-fan-curve examples/fan_operating_point_demo.json --output fan-operating-point-report.md

The v0.11 solver interpolates only between supplied fan pressure/airflow points and intersects them with an explicit system model `ΔP = ΔP_fixed + R·Q²`. If no crossing exists inside the supplied fan data, it reports that condition rather than extrapolating. See docs/FAN_SYSTEM_OPERATING_POINT.md.

## Solve a fan operating point from a reference duct network

    cleanroomx-fan-duct examples/fan_duct_network_demo.json

JSON output:

    cleanroomx-fan-duct examples/fan_duct_network_demo.json --format json

Write a Markdown report:

    cleanroomx-fan-duct examples/fan_duct_network_demo.json --output fan-duct-report.md

The v0.14 integration derives a quadratic system curve from the existing duct-section geometry and loss inputs plus a declared reference system airflow. Each section's reference airflow fraction is held fixed as total airflow changes. This is explicit proportional scaling, not a new pressure-balancing network solution. See docs/FAN_DUCT_NETWORK_INTEGRATION.md.

## Analyze a measured particle-recovery test

    cleanroomx-recovery-test examples/recovery_test_demo.json

JSON output:

    cleanroomx-recovery-test examples/recovery_test_demo.json --format json

Write a Markdown report:

    cleanroomx-recovery-test examples/recovery_test_demo.json --output recovery-report.md

The recovery workflow uses measured time/concentration samples directly. It records the first measured sample at or below the configured target, the measurement interval in which recovery occurred, optional traceability fields, and an optional maximum-time criterion. The log-linear fit is diagnostic only and does not replace the measured qualification result.

See docs/RECOVERY_TEST.md.

## Analyze uncertainty and input provenance

    cleanroomx-uncertainty examples/uncertainty_room_demo.json

JSON output:

    cleanroomx-uncertainty examples/uncertainty_room_demo.json --format json

Write a Markdown report:

    cleanroomx-uncertainty examples/uncertainty_room_demo.json --output uncertainty-report.md

The uncertainty workflow propagates user-supplied absolute bounds through room volume and supply ACH using deterministic conservative intervals. A configured minimum ACH is reported as pass only when the complete interval meets it, fail only when the complete interval is below it, and indeterminate when the requirement lies inside the interval.

See docs/UNCERTAINTY_PROVENANCE.md.

## Run uncertainty-aware qualification checks

    cleanroomx-qualification examples/qualification_uncertainty_demo.json

JSON output:

    cleanroomx-qualification examples/qualification_uncertainty_demo.json --format json

Write a Markdown report:

    cleanroomx-qualification examples/qualification_uncertainty_demo.json --output qualification-report.md

The v0.7 qualification workflow evaluates user-configured minimum/maximum requirements over the complete supplied uncertainty interval. Pressure cascades use the conservative differential interval `H_low - L_high` to `H_high - L_low`. A threshold overlap is `indeterminate`, not a pass.

See docs/QUALIFICATION_UNCERTAINTY.md.

## Analyze thermal/HVAC uncertainty

    cleanroomx-thermal-uncertainty examples/thermal_uncertainty_demo.json

JSON output:

    cleanroomx-thermal-uncertainty examples/thermal_uncertainty_demo.json --format json

Write a Markdown report:

    cleanroomx-thermal-uncertainty examples/thermal_uncertainty_demo.json --output thermal-uncertainty-report.md

The v0.10 workflow propagates user-supplied absolute bounds through explicit sensible/latent loads, cleanroom and makeup airflow, and optional supply-air temperature. It reports conservative cooling/heating capacity and governing-airflow intervals, plus optional available-capacity pass/fail/indeterminate checks.

See docs/THERMAL_UNCERTAINTY.md.

## Build an integrated engineering dossier

    cleanroomx-dossier examples/dossier_demo.json

JSON output:

    cleanroomx-dossier examples/dossier_demo.json --format json

Write a Markdown dossier:

    cleanroomx-dossier examples/dossier_demo.json --output dossier.md

The v0.13 dossier hashes every referenced input with SHA-256 and preserves component-specific fail, incomplete, indeterminate, not-checked, solved, outside-range, and no-intersection states. HVAC fan-curve duty checks from v0.12 are carried into the dossier automatically when present. An optional consistency block can reconcile verification and HVAC airflow using an explicit project-supplied percentage tolerance; CleanroomX does not invent a default tolerance. The dossier is a traceability/reporting layer, not cleanroom certification or fan/equipment acceptance.

Consistency demo:

    cleanroomx-dossier examples/dossier_consistency_demo.json

See docs/ENGINEERING_DOSSIER.md and docs/CROSS_MODULE_CONSISTENCY.md.

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

Next milestones are uncertainty propagation into recovery acceptance workflows, broader cross-module consistency coverage, general looped-network solving research, fan/system control-law studies, and later a desktop/web UI plus CFD adapters.

## Standards references

- ISO 14644-1:2015 — classification of air cleanliness by particle concentration.
- ISO 14644-3:2019 — cleanroom and clean-zone test methods.
- ISO 14644-4:2022 — cleanroom design, construction, and start-up.
- ASHRAE Handbook—Fundamentals — psychrometrics and duct design.
- ASHRAE Duct Fitting Database / Standard 120 resources — duct fitting resistance and loss coefficients.
- ASHRAE Design Guide for Cleanrooms.
- JCGM 100:2008 — Guide to the expression of uncertainty in measurement.
- JCGM 106:2012 — role of measurement uncertainty in conformity assessment.
- NIST Technical Note 1297 — Guidelines for Evaluating and Expressing the Uncertainty of NIST Measurement Results.

Always use the applicable purchased standard, local regulations, client URS/specification, qualification protocol, manufacturer data, and qualified engineering judgment for real projects.
