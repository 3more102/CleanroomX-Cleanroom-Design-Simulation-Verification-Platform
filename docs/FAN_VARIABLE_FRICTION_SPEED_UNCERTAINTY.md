# Fan-speed / variable-friction loop uncertainty

CleanroomX v0.39 combines the existing bounded fan-speed transformation with the v0.37 nonlinear fan/variable-friction uncertainty solver.

## What is evaluated

For every explicit fan speed ratio, CleanroomX scales the supplied reference fan-curve points using the existing affinity-law transform: airflow scales with speed and pressure scales with speed squared. It then evaluates every configured lower/upper uncertainty corner at that speed.

The bounded uncertainty dimensions remain the v0.37 inputs:

- fixed system pressure; and
- selected automatic-friction duct local-loss coefficients `K`.

Each speed/corner case rebuilds affected duct-geometry evidence and re-runs the full nonlinear Darcy-friction fan/network solve. No fixed equivalent resistance is substituted for the variable-friction network.

## Status behavior

A speed case is `complete` only when its nominal nonlinear operating point and every uncertainty corner solve inside the transformed supplied fan-curve range. Otherwise that speed is `indeterminate` and its complete airflow/pressure envelope is withheld.

The overall sweep is `screening_complete` only when every requested speed case is complete. Any indeterminate speed case makes the sweep `attention_required`.

`max_corner_cases` limits uncertainty corners per speed. `max_total_cases` additionally limits the complete speed × uncertainty matrix and defaults to 1024. CleanroomX rejects oversized studies rather than silently truncating them.

## Run

    cleanroomx-fan-loop-friction-speed-uncertainty examples/fan_variable_friction_speed_uncertainty_demo.json

JSON output:

    cleanroomx-fan-loop-friction-speed-uncertainty examples/fan_variable_friction_speed_uncertainty_demo.json --format json

Markdown output:

    cleanroomx-fan-loop-friction-speed-uncertainty examples/fan_variable_friction_speed_uncertainty_demo.json --output fan-speed-variable-friction-uncertainty.md

## Engineering boundary

The speed ratios are explicit scenarios, not inferred acceptable VFD limits. The uncertainty bounds are user-supplied deterministic engineering bounds, not statistical confidence intervals. The workflow does not infer fan-curve uncertainty, covariance, geometry manufacturing tolerances, controls, leakage, system effect, stall/surge acceptance, motor/VFD limits, transients, or manufacturer selection.
