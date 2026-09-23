# Fan-speed / variable-friction loop uncertainty

CleanroomX v0.41 composes explicit fan-speed scenarios with the canonical nonlinear fan/variable-friction uncertainty engine.

## Composition model

For every explicit speed ratio, CleanroomX transforms only the supplied reference fan-curve points using the existing affinity-law implementation: airflow scales with speed and pressure scales with speed squared. It then copies the validated canonical uncertainty study with that transformed curve and runs the existing nonlinear corner solver unchanged.

This composition is deliberately schema-preserving. The speed wrapper does not maintain a second list of supported uncertainty inputs. Every `UncertainValue` dimension present in the canonical fan/variable-friction uncertainty study contributes to the speed × uncertainty matrix automatically.

At the v0.40 baseline this includes bounded inputs for fixed pressure and selected automatic-friction duct local-loss, Darcy physical-property, and geometry inputs. Later canonical uncertainty dimensions can therefore flow through the speed workflow without duplicating their parsing or numerical implementation.

## Numerical behavior

For every speed and uncertainty corner, the canonical solver still:

1. rebuilds affected geometry evidence;
2. re-solves the complete variable-Darcy-friction loop at every fan/system airflow;
3. searches only inside the transformed supplied fan-curve range;
4. preserves `solved`, no-intersection, and numerical non-convergence states; and
5. withholds a complete envelope when the nominal case or any corner is unresolved.

A speed case is `complete` only when its nominal case and every configured uncertainty corner solve. The overall sweep is `screening_complete` only when every requested speed case is complete.

## Case guards

The canonical `max_corner_cases` limit remains active for each speed. The speed composition adds `max_total_cases` (default 1024) over the complete speed × uncertainty matrix. Oversized studies are rejected rather than silently truncated.

## Run

    cleanroomx-fan-loop-friction-speed-uncertainty examples/fan_variable_friction_speed_uncertainty_demo.json

JSON output:

    cleanroomx-fan-loop-friction-speed-uncertainty examples/fan_variable_friction_speed_uncertainty_demo.json --format json

Markdown output:

    cleanroomx-fan-loop-friction-speed-uncertainty examples/fan_variable_friction_speed_uncertainty_demo.json --output fan-speed-variable-friction-uncertainty.md

## Engineering boundary

Speed ratios are explicit engineering scenarios, not inferred acceptable VFD limits. Uncertainty intervals are user-supplied deterministic bounds, not probability distributions or confidence intervals. The workflow does not infer covariance, fan-curve uncertainty, manufacturing tolerances, controls, leakage, system effect, stall/surge acceptance, motor/VFD limits, transients, or manufacturer equipment selection.
