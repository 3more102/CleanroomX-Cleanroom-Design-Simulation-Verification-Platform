# CleanroomX

CleanroomX is an open engineering platform for **cleanroom design screening, simulation, verification, recovery qualification, uncertainty/provenance tracking, and preliminary HVAC analysis**. The project keeps calculations auditable and requirement-driven rather than hiding them behind a GUI.

## v0.39 engineering core

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
- Bounded fan/loop-network operating-point coupling for passive two-terminal fixed-resistance meshes, with no fan-curve extrapolation and full operating-flow re-solve.
- Deterministic fan/loop-network uncertainty corner analysis over user-supplied fixed-pressure and named edge-resistance bounds, with no fan-curve extrapolation and full loop re-solving at each bounded corner.
- Bounded fan-speed/VFD sweeps over fixed-resistance loop networks, re-solving the full mesh at each transformed fan-curve operating point.
- Explicit loop-network damper-resistance scenario studies using user-supplied per-edge resistance multipliers, with baseline/case flow redistribution and residual evidence.
- Optional loop-edge resistance derivation from explicit circular/rectangular duct geometry, Darcy friction, air density, and local K, with automatic friction resolved once at an explicit reference airflow.
- Optional variable-friction loop iteration for automatic roughness/viscosity geometry edges, with Reynolds/Darcy recomputation at solved edge flow, relaxation, closure reporting, explicit near-zero-flow handling, and pre-solve validation of stored automatic-friction evidence.
- Bounded fan/variable-friction loop coupling that re-solves the complete Darcy-friction network at every candidate fan/system airflow, with no fan-curve extrapolation, convergence diagnostics, and explicit non-converged states.
- Deterministic bounded uncertainty for fan/variable-friction loop coupling over explicit fixed-pressure plus selected automatic-friction local-loss, absolute-roughness, kinematic-viscosity, and air-density bounds, with full nonlinear re-solving at every corner and no envelope when any corner is unresolved.
- Explicit fan-speed/variable-friction loop sweeps that reuse the existing affinity-law scaling and v0.33 nonlinear coupling solver for every transformed speed case, preserving per-speed no-intersection/non-convergence states.
- Fan/system operating-point solving from supplied fan performance points and an explicit fixed-plus-quadratic system curve, without extrapolation.
- HVAC fan-curve design-duty verification at the required governing airflow and computed/entered static pressure, with bounded interpolation and no extrapolation.
- Fan/duct-network operating-point integration that derives a critical quadratic system resistance from explicit duct geometry, loss inputs, and fixed reference airflow fractions.
- Fan-driven passive parallel-network integration that derives equivalent resistance and pressure-balanced branch flows at the solved operating point.
- Bounded fan-speed/VFD sweeps using explicit fan affinity-law scaling of supplied reference curves, with no transformed-curve extrapolation.
- Deterministic bounded fan/system operating-point uncertainty across user-supplied fixed-pressure and quadratic-resistance intervals, with a complete airflow/pressure envelope only when every bounded corner is solved.
- Manifest-driven integrated engineering dossiers with SHA-256 source fingerprints across verification, HVAC/fan-duty screening, recovery, uncertainty workflows, fixed-resistance fan/network workflows, fan/variable-friction loop studies, fan-speed/variable-friction loop studies, nonlinear fan/variable-friction uncertainty analyses, and optional cross-module consistency.
- Standalone and dossier-integrated cross-module consistency checks for duplicated room airflow inputs, with explicit tolerance and optional identical-room-set enforcement.
- Dossier-integrated HVAC-to-fan operating-airflow consistency across fixed-resistance and variable-friction fan/network workflows plus evaluated nonlinear-uncertainty corners, using an explicit user-supplied absolute tolerance and preserving no-intersection or numerical non-convergence cases as unresolved/not-comparable.
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

The HVAC module is also a preliminary engineering model. The v0.8 branch-flow solver propagates fixed terminal demands through a directed tree by mass continuity, while the v0.9 standalone parallel-flow solver distributes a specified total flow across simple paths sharing the same pressure nodes under fixed R·Q² resistance assumptions. The v0.11 standalone fan-curve solver finds an operating point only inside user-supplied fan data against an explicit fixed-plus-quadratic system curve. The v0.12 HVAC fan-curve duty check instead tests the required HVAC airflow/static-pressure duty against bounded interpolation of supplied fan data; it does not infer an HVAC system curve or extrapolate fan performance. The v0.14 fan/duct-network workflow complements that design-duty check by deriving a fixed-ratio quadratic system curve from the path-based duct model and solving its bounded intersection with the supplied fan curve. The v0.16 fan-network workflow instead derives the equivalent resistance of passive common-pressure-node branches and solves the pressure-balanced branch split at the bounded fan operating point. The v0.19 fan-speed workflow applies user-requested affinity-law speed ratios to supplied reference fan-curve points and reuses the bounded operating-point solver at each transformed speed. The v0.23 looped-network workflow solves connected steady-state meshes from explicit fixed quadratic edge resistances and balanced node injections, including reverse-flow cases, while reporting continuity and pressure-law residuals. The fixed-resistance, damper-scenario, fan-coupled, and fan-speed/loop workflows remain bounded models rather than a general nonlinear duct-network/control solver. v0.30 adds a separate iterative Darcy-friction loop workflow for automatically derived geometry edges; CleanroomX still does not infer damper positions, leakage, system effect, acoustics, stall/surge limits, motor/VFD limits, or commissioning acceptance. It does not replace detailed coil selection, weather/load modeling, duct design, manufacturer fan selection, CFD, commissioning, certification, or qualified HVAC/cleanroom engineering review.

v0.21 automatic friction can resolve a Darcy factor from explicit roughness and kinematic viscosity at a known section/reference airflow for path-based and fixed-demand-tree calculations. It does not iteratively vary friction factor while solving a fan/network operating point, and the passive parallel-network workflows remain fixed-resistance models.

v0.26 fan/loop-network coupling reduces a passive two-terminal fixed-resistance mesh to its exact quadratic equivalent from a reference solve, intersects that equivalent with supplied fan data, and re-solves the full mesh at the bounded operating airflow. Internal external injections, variable-friction iteration, controls, leakage, and fan extrapolation remain outside this workflow.

v0.27 damper studies are explicit fixed-resistance scenarios only. A configured multiplier represents a user-declared increase in one edge's quadratic resistance; CleanroomX does not infer damper position, K-value, actuator behavior, control logic, or an automatically balanced setting.

v0.29 fan-speed/loop studies apply the existing affinity-law transformation to supplied fan data and reuse the fixed-resistance fan/loop solver at each explicit speed ratio. They do not infer acceptable VFD ranges, motor limits, variable-friction behavior, or manufacturer performance outside supplied data.

v0.30 variable-friction loop solving re-evaluates automatic Darcy friction from each edge's absolute solved airflow, relaxes geometry-derived resistance updates, and repeats the validated fixed-resistance loop solve until resistance closure is reached. Direct resistance inputs and user-supplied friction factors remain fixed; zero-flow branches are not assigned invented Reynolds values.

v0.31 fan/loop-network uncertainty evaluates explicit lower/upper bounds on fixed pressure and selected fixed loop-edge resistances around the v0.26 fan coupling. Every corner re-derives the equivalent network resistance and re-solves the full fixed-resistance loop. If any corner falls outside the supplied fan curve, the complete operating-point and internal edge-flow corner ranges are withheld. Internal edge-flow min/max values are evaluated-corner evidence, not guaranteed continuous-box extrema.

v0.32 integrates v0.31 fan/loop-network uncertainty and v0.29 fan-speed/loop studies into engineering dossiers. Source inputs are SHA-256 fingerprinted; indeterminate uncertainty corners and unresolved speed cases propagate into dossier attention state, while missing uncertainty provenance remains visible as unresolved traceability. The dossier does not turn these screening workflows into fan acceptance, commissioning, certification, or statistical uncertainty claims.

v0.33 couples supplied fan data directly to the v0.30 variable-friction loop solver. Every fan-curve endpoint check and every bounded root-search airflow re-solves the complete network and iterates automatic Darcy friction to the configured resistance-closure tolerance. Fan pressure remains piecewise-linear only inside supplied data. A network iteration failure is reported as `non_converged`; no operating point is fabricated. The workflow remains a steady engineering network model rather than CFD and does not infer fan/VFD limits, controls, leakage, system effect, stall/surge acceptance, or equipment selection.

v0.34 applies the existing affinity-law fan-curve transform to each explicit speed ratio and then delegates each transformed curve to the v0.33 variable-friction coupling solver. Each speed case preserves transformed supplied-data bounds, complete network re-solving, Darcy resistance closure, fan/system residuals, and independent solved/no-intersection/non-converged status. No acceptable VFD range or motor limit is inferred.

v0.35 integrates the v0.33 and v0.34 nonlinear fan/loop workflows into engineering dossiers. Inputs are SHA-256 fingerprinted, solver diagnostics and convergence evidence are preserved in JSON and Markdown, HVAC operating-airflow consistency includes solved nonlinear cases, and `non_converged` cases always propagate as dossier attention rather than PASS.

v0.36 hardens automatic-friction evidence validation before any network iteration. Geometry-derived edges that claim automatic roughness/viscosity friction must carry complete finite stored geometry, reference-flow, and friction evidence; malformed evidence is rejected even when the solved branch flow is near zero.

v0.37 adds deterministic bounded uncertainty around the nonlinear fan/variable-friction loop workflow. It varies explicit fixed pressure and selected automatic-friction duct local-loss coefficients, rebuilds affected geometry evidence, and re-solves Darcy friction and the bounded fan/system intersection at every corner. Complete operating-point and branch-flow corner ranges are reported only when the nominal case and every corner solve; corner ranges are evidence over evaluated combinations, not statistical or guaranteed continuous-box extrema.

v0.38 integrates the v0.37 nonlinear uncertainty workflow into engineering dossiers. Referenced uncertainty inputs are SHA-256 fingerprinted, complete corner evidence remains available in JSON, Markdown surfaces corner counts and bounded airflow envelopes, indeterminate analyses become dossier attention items, and missing provenance remains a separate unresolved traceability condition. When HVAC/fan operating-airflow consistency is configured, each evaluated nonlinear uncertainty corner is checked independently; unresolved corners remain not comparable.

v0.39 extends nonlinear fan/variable-friction uncertainty from fixed pressure and local-loss K to user-bounded absolute roughness, kinematic viscosity, and air density on automatic-friction geometry edges. Every physical-input corner rebuilds the affected duct evidence before the complete Darcy-friction fan/network solve; nominal values continue to come only from the loop geometry, invalid physical bounds are rejected, and the corner limit remains explicit.

The uncertainty workflows use deterministic user-supplied input intervals. They are not statistical measurement-uncertainty budgets, do not invent tolerances or acceptance limits, and do not replace calibration records, project qualification procedures, or project/regulatory conformity decision rules. Standalone psychrometric uncertainty evaluates every unique corner of the configured dry-bulb/relative-humidity/pressure box. Thermal uncertainty can use the same bounded room/outdoor states and propagates their endpoint corners into makeup-air load and sensible-airflow intervals. Fan/system uncertainty evaluates every unique fixed-pressure/resistance corner and withholds a complete operating-point envelope if any corner would require fan-curve extrapolation. The conservative fan/system envelope is limited to airflow and pressure; air-power corner extrema are not claimed as a complete bound. These workflows do not model covariance, hourly weather/load behavior, variable controls, or equipment selection.

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

The v0.25 solver handles connected steady-state meshes with arbitrary loops using fixed quadratic edge laws `ΔP = R·Q·|Q|` and explicitly balanced node injections. `R` may be supplied directly or derived from explicit duct geometry, density, Darcy factor, and local K. Automatic friction may be resolved once at an explicit reference airflow, but resistance is not iterated with solved loop flow. See docs/LOOPED_NETWORK_SOLVER.md.

Geometry-derived resistance demo:

    cleanroomx-loop-flow examples/looped_network_geometry_demo.json

## Solve a looped network with variable Darcy friction

    cleanroomx-loop-friction examples/variable_friction_loop_demo.json

JSON output:

    cleanroomx-loop-friction examples/variable_friction_loop_demo.json --format json

Write a Markdown report:

    cleanroomx-loop-friction examples/variable_friction_loop_demo.json --output variable-friction-loop-report.md

The v0.30 workflow iterates only geometry-derived edges configured with automatic roughness/viscosity friction inputs. Explicit resistance and user-supplied-friction edges remain fixed. See docs/VARIABLE_FRICTION_LOOP.md.

## Solve a fan-driven loop with variable Darcy friction

    cleanroomx-fan-loop-friction examples/fan_variable_friction_loop_demo.json
    cleanroomx-fan-loop-friction-speed examples/fan_variable_friction_speed_demo.json

JSON output:

    cleanroomx-fan-loop-friction examples/fan_variable_friction_loop_demo.json --format json

Write a Markdown report:

    cleanroomx-fan-loop-friction examples/fan_variable_friction_loop_demo.json --output fan-variable-loop-report.md

The v0.33 workflow searches only inside the supplied fan curve. At every fan/system evaluation it scales the two-terminal through-flow, solves the complete loop, recomputes automatic Darcy friction from solved branch airflow, and iterates resistance closure before comparing fan and system pressure. Fixed-resistance networks remain compatible with the existing v0.26 result. See docs/FAN_VARIABLE_FRICTION_LOOP.md.

## Solve a fan-driven looped network

    cleanroomx-fan-loop examples/fan_loop_network_demo.json

JSON output:

    cleanroomx-fan-loop examples/fan_loop_network_demo.json --format json

Write a Markdown report:

    cleanroomx-fan-loop examples/fan_loop_network_demo.json --output fan-loop-report.md

The v0.26 workflow accepts a passive two-terminal v0.25 loop network, derives its equivalent fixed quadratic resistance from a reference through-flow, intersects that system law with supplied fan data without extrapolation, and re-solves the original loop at the operating airflow. See docs/FAN_LOOP_NETWORK.md.

## Analyze bounded fan/loop-network uncertainty

    cleanroomx-fan-loop-uncertainty examples/fan_loop_uncertainty_demo.json

JSON output:

    cleanroomx-fan-loop-uncertainty examples/fan_loop_uncertainty_demo.json --format json

Write a Markdown report:

    cleanroomx-fan-loop-uncertainty examples/fan_loop_uncertainty_demo.json --output fan-loop-uncertainty-report.md

The v0.31 workflow evaluates every unique lower/upper corner of user-supplied fixed-pressure and named loop-edge resistance bounds. It re-derives the equivalent fixed-resistance loop law and re-solves the full mesh at each bounded fan operating point. A complete operating-point and internal edge-flow corner range is reported only when the nominal case and every configured corner intersect the supplied fan curve without extrapolation. See docs/FAN_LOOP_UNCERTAINTY.md.

## Sweep fan speed over a looped network

    cleanroomx-fan-loop-speed examples/fan_loop_speed_demo.json

JSON output:

    cleanroomx-fan-loop-speed examples/fan_loop_speed_demo.json --format json

Write a Markdown report:

    cleanroomx-fan-loop-speed examples/fan_loop_speed_demo.json --output fan-loop-speed-report.md

The v0.29 workflow applies explicit fan-speed ratios to the supplied reference fan curve using the existing affinity-law transform, solves each transformed curve against the same passive fixed-resistance two-terminal loop, and re-solves the full mesh at every bounded operating point. See docs/FAN_LOOP_SPEED_STUDY.md.

## Run loop damper-resistance scenarios

    cleanroomx-damper-study examples/damper_study_demo.json

JSON output:

    cleanroomx-damper-study examples/damper_study_demo.json --format json

Write a Markdown report:

    cleanroomx-damper-study examples/damper_study_demo.json --output damper-study-report.md

The v0.27 workflow solves the unchanged baseline loop and each explicit throttling case, where selected edge resistances are multiplied by user-supplied finite factors greater than or equal to 1. It reports the resulting edge-flow redistribution and solver residuals without inferring damper position or automatic control. See docs/DAMPER_STUDY.md.

## Solve a fan/system operating point

    cleanroomx-fan-curve examples/fan_operating_point_demo.json

JSON output:

    cleanroomx-fan-curve examples/fan_operating_point_demo.json --format json

Write a Markdown report:

    cleanroomx-fan-curve examples/fan_operating_point_demo.json --output fan-operating-point-report.md

The v0.11 solver interpolates only between supplied fan pressure/airflow points and intersects them with an explicit system model `ΔP = ΔP_fixed + R·Q²`. If no crossing exists inside the supplied fan data, it reports that condition rather than extrapolating. See docs/FAN_SYSTEM_OPERATING_POINT.md.

## Analyze bounded fan/system uncertainty

    cleanroomx-fan-uncertainty examples/fan_uncertainty_demo.json

JSON output:

    cleanroomx-fan-uncertainty examples/fan_uncertainty_demo.json --format json

Write a Markdown report:

    cleanroomx-fan-uncertainty examples/fan_uncertainty_demo.json --output fan-uncertainty-report.md

The v0.24 workflow holds the supplied fan curve fixed, evaluates every unique lower/upper corner of user-supplied fixed-pressure and quadratic-resistance bounds, and reports an airflow/pressure operating-point envelope only when every bounded corner is solved inside the supplied fan-curve range. See docs/FAN_SYSTEM_UNCERTAINTY.md.

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

HVAC/fan operating-airflow consistency demo:

    cleanroomx-dossier examples/dossier_fan_airflow_consistency_demo.json

The v0.22 check compares the analyzed HVAC total governing airflow with every included solved fan operating point, including individual fan-speed cases. Unsolved cases remain `not_comparable`; they are not converted into failures. The absolute tolerance is a project input, not a built-in engineering or standards limit. See docs/HVAC_FAN_AIRFLOW_CONSISTENCY.md.

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

Next milestones are dossier integration for fan/loop uncertainty and fan-speed loop studies, followed by desktop/web UI work and CFD adapters.

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

v0.37 adds deterministic bounded corner uncertainty around the nonlinear fan/variable-friction loop solver for explicit fixed-pressure and selected automatic-friction local-loss bounds. Every corner rebuilds the affected geometry evidence and re-runs the full Darcy-friction fan/network solve. Complete operating-point and internal edge-flow envelopes are reported only when the nominal case and every evaluated corner solve inside the supplied fan-curve range; no-intersection or numerical non-convergence remains indeterminate. The analysis is deterministic corner evidence, not statistical uncertainty propagation, and does not infer K-factor uncertainty, covariance, geometry manufacturing tolerances, fan-curve uncertainty, controls, leakage, commissioning acceptance, or certification.
