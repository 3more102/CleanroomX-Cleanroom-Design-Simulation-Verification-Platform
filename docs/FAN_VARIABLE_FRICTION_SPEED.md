# Fan-Speed / Variable-Friction Loop Coupling

CleanroomX v0.34 extends the bounded v0.33 fan/variable-friction loop workflow to explicit user-supplied fan-speed ratios.

For each configured speed ratio the workflow:

1. transforms only the supplied reference fan-curve points with the existing `scale_fan_curve_for_speed` affinity-law implementation;
2. preserves the transformed fan-curve airflow bounds;
3. delegates the transformed curve to the v0.33 bounded fan/variable-friction loop solver;
4. re-solves the complete two-terminal loop at every evaluated total airflow;
5. recomputes automatic Darcy friction from solved branch airflow;
6. preserves explicit-resistance and user-supplied-friction edges as fixed;
7. reports solved, no-intersection, and numerical non-convergence states independently.

No fan-curve extrapolation is performed.

## Input

The JSON input contains:

- `name`
- `reference_fan_curve`
- `speed_ratios`
- optional `reference_speed_rpm`
- `fan_discharge_node`
- `fan_suction_node`
- optional nonnegative `fixed_pressure_pa`
- `loop_network`
- optional `solver` controls identical to the v0.33 coupled solver

The loop must satisfy the existing passive two-terminal fan/loop validation: the configured discharge and suction injections are equal/opposite and all other external injections are zero.

Automatic variable-friction behavior is activated only for duct-geometry edges that contain explicit absolute roughness and kinematic viscosity evidence. Direct resistance inputs and duct-geometry edges with a user-supplied friction factor remain fixed.

## Solver evidence

Each speed case exposes:

- speed ratio and optional rpm;
- transformed fan-curve airflow range;
- case status;
- operating airflow and fan pressure when solved;
- loop-network and total system pressure;
- fan-minus-system pressure residual;
- complete operating loop solution and signed edge flows;
- automatic-friction edge closure evidence;
- Reynolds/friction evidence inherited from the v0.30 loop solver;
- nonlinear outer-iteration count;
- maximum relative resistance-closure error;
- node continuity residual;
- edge pressure-law residual;
- termination reason.

The overall study is `screening_complete` only when every configured speed case is solved. Any `no_intersection_in_supplied_range` or `non_converged` case produces `attention_required`.

## CLI

```text
cleanroomx-fan-loop-friction-speed examples/fan_variable_friction_speed_demo.json
cleanroomx-fan-loop-friction-speed examples/fan_variable_friction_speed_demo.json --format json
```

## Engineering boundaries

Affinity scaling is applied only to the supplied reference points: airflow scales with speed ratio and pressure with speed ratio squared. CleanroomX does not infer an acceptable VFD range, motor limit, drive efficiency, fan efficiency, stall/surge boundary, system-effect correction, control action, damper position, leakage, transient behavior, or manufacturer acceptance.

The reported fluid air power in solved cases is `Q × ΔP`. It is not shaft power or electrical input power unless explicit efficiency models are supplied by a separate workflow.
