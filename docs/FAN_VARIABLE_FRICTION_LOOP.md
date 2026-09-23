# Fan / variable-friction loop coupling

CleanroomX v0.33 couples a supplied fan pressure/airflow curve directly to the existing two-terminal loop-network solver while re-evaluating automatic Darcy friction at every airflow used during the operating-point search.

This workflow is intentionally separate from the v0.26 fixed-resistance fan/loop solver. v0.26 is exact for a network whose edge laws remain fixed quadratic laws. v0.33 is for loop edges whose resistance was derived from explicit duct geometry, absolute roughness, and kinematic viscosity and therefore needs the v0.30 Darcy-friction closure iteration as airflow changes.

## Model

For each candidate total airflow, CleanroomX:

1. scales the declared equal/opposite fan discharge and suction injections to the candidate airflow;
2. solves the complete loop network;
3. re-evaluates Darcy friction for every automatic-friction geometry edge at its solved absolute branch airflow;
4. iterates resistance until the configured relative closure tolerance is reached;
5. calculates the fan-terminal loop pressure difference;
6. adds the explicit fixed-pressure term;
7. compares that system pressure with the piecewise-linear fan pressure inside the supplied curve.

The fan operating point is found only inside a supplied fan-curve segment. No fan-curve extrapolation is performed.

For automatic geometry edges, the existing CleanroomX Darcy-Weisbach resistance model is reused:

`R = 0.5 rho (f L / Dh + K) / A^2`

with pressure loss represented as `deltaP = R Q |Q|`. The Darcy factor is recomputed from the existing Reynolds/roughness model at each non-negligible solved edge flow. Explicit-resistance edges and geometry edges with a user-supplied friction factor remain fixed.

## Input

See `examples/fan_variable_friction_loop_demo.json`.

Required study fields are:

- `name`;
- `fan_curve` with at least two strictly increasing airflow points and non-increasing pressure;
- `loop_network`;
- `fan_discharge_node`;
- `fan_suction_node`.

The fan nodes must use equal/opposite nonzero reference injections and every other node must have zero external injection. The reference injection sets topology and scaling; it is not assumed to be the final fan operating airflow.

Optional `fixed_pressure_pa` is nonnegative and is added to the solved loop pressure.

Optional `solver` fields are:

- `resistance_relative_tolerance` (default `1e-6`);
- `relaxation` in `(0, 1]` (default `0.5`);
- `near_zero_airflow_m3_h` (default `1e-6`);
- `max_outer_iterations` (default `50`);
- `mass_balance_tolerance_m3_h` (default `1e-6`);
- `max_newton_iterations` (default `100`);
- `operating_pressure_tolerance_pa` (default `1e-6`);
- `max_operating_iterations` (default `80`).

Unknown solver options are rejected.

## Result states

- `solved`: a fan/system intersection was found inside the supplied fan-curve range and the variable-friction network converged.
- `no_intersection_in_supplied_range`: all required network evaluations converged, but no bounded fan/system crossing exists.
- `non_converged`: the variable-friction network or the bounded operating-point iteration did not satisfy its configured convergence limit.

An unresolved state never produces a fabricated operating point.

## Diagnostics

A solved result includes:

- fan operating airflow and pressure;
- loop pressure and total system pressure;
- fan/system residual;
- interpolation segment;
- fluid air power `Q * deltaP` only;
- complete operating network solution;
- node continuity and edge pressure-law residuals;
- variable-friction outer-iteration count;
- resistance-closure error;
- edge Reynolds/friction evidence;
- supplied fan-point system checks;
- operating-point termination reason;
- a supplied-point fan-minus-system residual-topology audit with expected/evaluated point counts, complete/partial point coverage, tolerance contacts, strict sign-change segments, adjacent residual transitions, sampled monotonic non-increasing behavior within the configured pressure tolerance, and discrete candidate-crossing features;
- for solved cases, selected-candidate provenance containing the documented selection policy, selected feature, zero-based priority rank, number of additional sampled candidates, and whether the selected feature is the only discrete candidate.
- terminal operating-point root-search interval provenance: bounded-bisection cases retain initial/final sign brackets, terminal airflow span, and contraction ratio; supplied-point tolerance contacts are explicitly marked as non-bisection cases with no fabricated bracket width.

The reported air power is fluid power, not shaft or electrical input.

The residual-topology audit uses only supplied fan-curve points already evaluated by the bounded nonlinear solver. A candidate feature is a supplied point within the configured root tolerance or a strict positive-to-negative sign-change segment. Candidate-feature counts and sampled monotonicity are diagnostic evidence only: they do not count or prove continuous fan/system intersections, guarantee uniqueness between supplied points, establish dynamic stability, identify stall/surge boundaries, or define manufacturer/equipment acceptance. v0.63 additionally preserves the exact deterministic selection policy and selected discrete feature for solved results so the chosen bounded root is auditable when more than one sampled candidate feature exists.

v0.65 additionally retains the root-search geometry used to terminate the operating-point solve. For bounded bisection, the solver records the initial supplied-point sign-change bracket and the final sign-consistent bracket after the accepted midpoint has been incorporated by residual sign. The resulting terminal span and contraction ratio are numerical convergence provenance only. A direct supplied-point tolerance contact is recorded as such and does not receive a bisection span. These records do not define physical airflow uncertainty, interpolation error, dynamic stability, stall/surge margin, manufacturer operating region, commissioning/certification status, or equipment acceptance.

## CLI

```text
cleanroomx-fan-loop-friction examples/fan_variable_friction_loop_demo.json
cleanroomx-fan-loop-friction examples/fan_variable_friction_loop_demo.json --format json
cleanroomx-fan-loop-friction examples/fan_variable_friction_loop_demo.json --output fan-variable-loop.md
```

The CLI exits with code 0 only for `solved`; unresolved/non-converged studies return code 2.

## Engineering boundary

This is a steady incompressible engineering network model, not CFD. It does not infer damper position, leakage, system effect, acoustic performance, fan stall/surge boundaries, motor/VFD limits, controls, transients, or manufacturer acceptance. The supplied fan data and all engineering inputs remain the user's responsibility.


## Automatic-friction evidence validation

Before solving, every geometry edge identified as automatic-friction is validated against its stored resistance evidence. The solver requires complete finite geometry, density/local-loss, roughness, kinematic-viscosity, positive reference-airflow, hydraulic-diameter/area, and positive stored friction-factor evidence. This validation occurs before near-zero-flow freezing, so a zero-flow branch cannot hide malformed automatic-friction provenance.
