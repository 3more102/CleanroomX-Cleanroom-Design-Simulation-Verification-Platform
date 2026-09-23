# CleanroomX

CleanroomX is an open engineering platform for **cleanroom design screening, simulation, verification, recovery qualification, uncertainty/provenance tracking, and preliminary HVAC analysis**. The project keeps calculations auditable and requirement-driven rather than hiding them behind a GUI.

## v0.22 engineering core

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
- Optional Darcy friction-factor resolution from explicit absolute roughness and kinematic viscosity, with Reynolds-number evidence and preserved manual-factor compatibility.
- Circular and rectangular duct geometry with hydraulic-diameter reporting.
- Critical-path selection across user-defined duct paths and direct integration into fan duty.
- Directed supply-tree branch-flow solving from explicit terminal demands with continuity residuals and terminal critical-path analysis.
- Passive parallel-path airflow solving for simple common-pressure-node networks using explicit fixed resistances.
- Fixed-resistance looped airflow-network solving for connected meshes with arbitrary loops, signed reverse flow, node-continuity residuals, and edge pressure-law residuals.
- Fan/system operating-point solving from supplied fan performance points and an explicit fixed-plus-quadratic system curve, without extrapolation.
- HVAC fan-curve design-duty verification at the required governing airflow and computed/entered static pressure, with bounded interpolation and no extrapolation.
- Fan/duct-network operating-point integration that derives a critical quadratic system resistance from explicit duct geometry, loss inputs, and fixed reference airflow fractions.
- Fan-driven passive parallel-network integration that derives equivalent resistance and pressure-balanced branch flows at the solved operating point.
- Bounded fan-speed/VFD sweeps using explicit fan affinity-law scaling of supplied reference curves, with no transformed-curve extrapolation.
- Manifest-driven integrated engineering dossiers with SHA-256 source fingerprints across verification, HVAC/fan-duty screening, recovery, room/qualification/thermal/psychrometric uncertainty, standalone fan/system studies, reference-flow fan/duct studies, fan-driven passive parallel-network studies, fan-speed affinity-law studies, and optional cross-module consistency.
- Standalone and dossier-integrated cross-module consistency checks for duplicated room airflow inputs, with explicit tolerance and optional identical-room-set enforcement.
- Measured particle-recovery qualification records with project-configured target, maximum recovery time, and optional per-sample absolute concentration uncertainty.
- Conservative recovery decisions with pass/fail/indeterminate/incomplete/not-checked status plus traceability metadata.
- Log-linear decay diagnostics and estimated effective ACH as screening outputs only.
- Conservative interval propagation for uncertain room dimensions and supply airflow.
- Provenance records for engineering input source, reference, revision/date, and uncertainty basis.
- Robust minimum-ACH decisions with pass/fail/indeterminate/not-checked status.
- Conservative uncertainty-aware minimum/maximum qualification checks for measured quantities such as pressure and particle concentration.
- Worst-case interval propagation for room-to-room pressure cascades, with `indeterminate` when an acceptance threshold is overlapped.
- Deterministic thermal/HVAC uncertainty intervals for explicit loads, airflow, supply-air temperature, room/outdoor psychrometric states, and equipment-capacity screening.
- Deterministic psychrometric-state uncertainty envelopes for dry-bulb temperature, relative humidity, pressure, humidity ratio, enthalpy, specific volume, dew point, and moist-air specific heat.
- JSON input, Markdown/JSON reports, CLI workflows, tests, and GitHub Actions CI on Python 3.11–3.13.

## Important engineering boundary

CleanroomX does **not** claim that ACH, room pressure, a pressure cascade, airflow surplus, a fitted recovery model, or a simple decay model determines ISO cleanroom classification. ISO 14644-1 classifies air cleanliness by airborne particle concentration. ISO 14644-3 provides cleanroom test methods. Project, process, safety, and regulatory requirements can add other criteria.

CleanroomX therefore does not embed unofficial ISO classification, ACH, pressure-cascade, airflow-surplus, filter-pressure-drop, duct-friction, fitting-loss, fan-sizing, particle-target, or recovery-time limits. Numeric requirements are supplied by the user from the applicable licensed standard, client URS/specification, qualification protocol, process design basis, manufacturer data, or regulator.

The decay/recovery function is a **screening model**, not CFD. It assumes a well-mixed room and first-order effective removal and does not model particle generation, deposition, leakage, local airflow patterns, or transient HVAC controls.

The HVAC module is also a preliminary engineering model. The v0.8 branch-flow solver propagates fixed terminal demands through a directed tree by mass continuity, while the v0.9 standalone parallel-flow solver distributes a specified total flow across simple paths sharing the same pressure nodes under fixed R·Q² resistance assumptions. The v0.11 standalone fan-curve solver finds an operating point only inside user-supplied fan data against an explicit fixed-plus-quadratic system curve. The v0.12 HVAC fan-curve duty check instead tests the required HVAC airflow/static-pressure duty against bounded interpolation of supplied fan data; it does not infer an HVAC system curve or extrapolate fan performance. The v0.14 fan/duct-network workflow complements that design-duty check by deriving a fixed-ratio quadratic system curve from the path-based duct model and solving its bounded intersection with the supplied fan curve. The v0.16 fan-network workflow instead derives the equivalent resistance of passive common-pressure-node branches and solves the pressure-balanced branch split at the bounded fan operating point. The v0.19 fan-speed workflow applies user-requested affinity-law speed ratios to supplied reference fan-curve points and reuses the bounded operating-point solver at each transformed speed. The v0.22 looped-network workflow solves connected steady-state meshes from explicit fixed quadratic edge resistances and balanced node injections, including reverse-flow cases, while reporting continuity and pressure-law residuals. These remain bounded models rather than a general geometry-derived, variable-friction, controlled HVAC-network solver; CleanroomX does not infer damper positions, leakage, system effect, acoustics, stall/surge limits, motor/VFD limits, or commissioning acceptance. It does not replace detailed coil selection, weather/load modeling, duct design, manufacturer fan selection, CFD, commissioning, certification, or qualified HVAC/cleanroom engineering review.

v0.21 automatic friction can resolve a Darcy factor from explicit roughness and kinematic viscosity at a known section/reference airflow for path-based and fixed-demand-tree calculations. It does not iteratively vary friction factor while solving a fan/network operating point, and the passive parallel-network workflows remain fixed-resistance models.

v0.22 looped-network solving uses explicit fixed quadratic edge resistances with balanced node injections. It solves relative node pressures and signed edge flows, but does not derive mesh resistance from duct geometry, vary friction during the solve, or couple fan curves, dampers, controls, or leakage into the mesh.

The uncertainty workflows use deterministic user-supplied input intervals. They are not statistical measurement-uncertainty budgets, do not invent tolerances or acceptance limits, and do not replace calibration records, project qualification procedures, or project/regulatory conformity decision rules. Standalone psychrometric uncertainty evaluates every unique corner of the configured dry-bulb/relative-humidity/pressure box. Thermal uncertainty can use the same bounded room/outdoor states and propagates their endpoint corners into makeup-air load and sensible-airflow intervals. These workflows do not model covariance, hourly weather/load behavior, or equipment selection.

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

Automatic Darcy-friction demo (explicit roughness and kinematic viscosity):

    cleanroomx-hvac examples/auto_friction_duct_demo.json

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

## Solve a fixed-resistance looped airflow network

    cleanroomx-loop-flow examples/looped_network_demo.json

JSON output:

    cleanroomx-loop-flow examples/looped_network_demo.json --format json

Write a Markdown report:

    cleanroomx-loop-flow examples/looped_network_demo.json --output looped-network-report.md

The v0.22 solver handles connected steady-state meshes with arbitrary loops when every edge uses an explicit fixed quadratic law `ΔP = R·Q·|Q|` and node injections are explicitly balanced. It reports signed flow direction, relative node pressure, node-continuity residuals, and edge pressure-law residuals. It does not infer duct geometry, friction factors, fans, dampers, controls, leakage, or transient behavior. See docs/LOOPED_NETWORK_SOLVER.md.

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

## Solve a fan-driven passive parallel network

    cleanroomx-fan-network examples/fan_parallel_network_demo.json

JSON output:

    cleanroomx-fan-network examples/fan_parallel_network_demo.json --format json

Write a Markdown report:

    cleanroomx-fan-network examples/fan_parallel_network_demo.json --output fan-network-report.md

The v0.16 workflow derives an equivalent fixed R·Q² resistance from passive branches that share common upstream/downstream pressure nodes, combines it with an explicit fixed-pressure term, solves the bounded fan/system intersection, and then redistributes the operating airflow across the original branches using equal pressure drop. It reports mass- and equal-pressure residuals and does not extrapolate supplied fan data. See docs/FAN_NETWORK_INTEGRATION.md.

## Sweep fan speed with affinity-law scaling

    cleanroomx-fan-speed examples/fan_speed_sweep_demo.json

JSON output:

    cleanroomx-fan-speed examples/fan_speed_sweep_demo.json --format json

Write a Markdown report:

    cleanroomx-fan-speed examples/fan_speed_sweep_demo.json --output fan-speed-report.md

The v0.19 workflow scales only the supplied reference fan-curve points for explicit user-provided speed ratios using airflow ∝ speed and pressure ∝ speed², reports the cubic affinity power ratio, and solves each transformed curve against the explicit system curve without extrapolation. It does not infer acceptable fan/VFD speed limits or motor input power. See docs/FAN_SPEED_STUDY.md.

## Analyze a measured particle-recovery test

    cleanroomx-recovery-test examples/recovery_test_demo.json

JSON output:

    cleanroomx-recovery-test examples/recovery_test_demo.json --format json

Write a Markdown report:

    cleanroomx-recovery-test examples/recovery_test_demo.json --output recovery-report.md

The recovery workflow uses measured time/concentration samples directly and optionally accepts an absolute concentration uncertainty for each sample. PASS requires a complete sample uncertainty interval at or below the target by the configured maximum time; target overlap at the deadline is INDETERMINATE. The original nominal recovery time/window remains reported for traceability. The log-linear fit uses nominal values only and remains diagnostic.

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

## Analyze psychrometric-state uncertainty

    cleanroomx-psychrometric-uncertainty examples/psychrometric_uncertainty_demo.json

JSON output:

    cleanroomx-psychrometric-uncertainty examples/psychrometric_uncertainty_demo.json --format json

Write a Markdown report:

    cleanroomx-psychrometric-uncertainty examples/psychrometric_uncertainty_demo.json --output psychrometric-uncertainty-report.md

The v0.15 workflow propagates user-supplied absolute bounds for dry-bulb temperature, relative humidity, and total pressure through the existing CleanroomX psychrometric equations by evaluating every unique input-box corner. It reports deterministic envelopes for vapor pressure, humidity ratio, enthalpy, specific volume, dew point, and moist-air specific heat.

See docs/PSYCHROMETRIC_UNCERTAINTY.md.

## Build an integrated engineering dossier

    cleanroomx-dossier examples/dossier_demo.json

JSON output:

    cleanroomx-dossier examples/dossier_demo.json --format json

Write a Markdown dossier:

    cleanroomx-dossier examples/dossier_demo.json --output dossier.md

The v0.20 dossier hashes every referenced input with SHA-256 and covers verification, HVAC/fan-duty screening, recovery, room/qualification/thermal/psychrometric uncertainty, standalone fan/system studies, reference-flow fan/duct-network studies, fan-driven passive parallel-network studies, fan-speed affinity-law studies, and optional v0.17 verification/HVAC consistency checks. Recovery INDETERMINATE, fan no-intersection, consistency failure, and unresolved comparability states are preserved rather than promoted to pass. The dossier is a traceability/reporting layer, not cleanroom certification or fan/equipment acceptance.

Consistency-integrated dossier demo:

    cleanroomx-dossier examples/dossier_consistency_demo.json

See docs/ENGINEERING_DOSSIER.md.

## Check cross-module input consistency

    cleanroomx-consistency examples/facility_project.json examples/consistency_hvac_demo.json

Allow an explicit absolute data-consistency tolerance:

    cleanroomx-consistency examples/facility_project.json examples/consistency_hvac_demo.json --airflow-tolerance-m3-h 5

Require identical room-name sets:

    cleanroomx-consistency examples/facility_project.json examples/consistency_hvac_demo.json --require-same-room-set

The v0.17 checker matches rooms by exact name and compares verification supply airflow against HVAC cleanroom airflow. Its tolerance is supplied by the user and is not a standards-derived engineering acceptance limit. See docs/CROSS_MODULE_CONSISTENCY.md.

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

Next milestones are deriving looped-network resistances from explicit duct geometry, bounded fan/mesh coupling, closed-loop control studies, and later a desktop/web UI plus CFD adapters.

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
