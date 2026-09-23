# Fan / loop-network uncertainty

CleanroomX v0.27 adds deterministic bounded uncertainty analysis to the v0.26 fan-driven two-terminal loop-network workflow.

## Inputs

The nominal fan curve and loop network use the same v0.26/v0.25 models. Uncertainty is supplied explicitly for:

- fixed pressure, as an absolute lower/upper interval around a nominal value;
- any loop-edge quadratic resistance, using an absolute uncertainty attached by edge name.

Edges without a configured resistance uncertainty remain fixed at their nominal value. Geometry-derived and automatic-friction edges are supported through the existing loop-network loader; their nominal derived resistance is frozen before any explicitly configured resistance uncertainty is applied.

## Corner analysis

For each uncertain input, CleanroomX evaluates the unique lower and upper values. It solves every resulting corner by:

1. rebuilding the loop with that corner's fixed edge resistances;
2. deriving the two-terminal equivalent loop resistance from the reference through-flow;
3. intersecting the equivalent system curve with the supplied fan curve without extrapolation;
4. re-solving the full loop at the corner operating airflow when an intersection exists.

Zero-width intervals collapse to one value, so duplicate corners are not generated.

The analysis defaults to `max_corner_cases = 256`. Inputs that would create more cases are rejected instead of silently truncating the uncertainty space.

## Result status

A `complete` result requires the nominal case and every configured corner to produce a bounded fan/system intersection. CleanroomX then reports the min/max corner span for operating airflow, system pressure, and equivalent loop resistance.

If the nominal case or any corner has no intersection inside the supplied fan data, the result is `indeterminate` and no complete operating-point envelope is reported.

Solved edge airflows are retained per corner as diagnostic evidence. They are not claimed as conservative continuous-interval bounds for every interior uncertainty combination.

## Run

    cleanroomx-fan-loop-uncertainty examples/fan_loop_uncertainty_demo.json

JSON output:

    cleanroomx-fan-loop-uncertainty examples/fan_loop_uncertainty_demo.json --format json

Markdown report:

    cleanroomx-fan-loop-uncertainty examples/fan_loop_uncertainty_demo.json --output fan-loop-uncertainty-report.md

## Engineering boundary

This is deterministic user-supplied interval screening. It does not infer uncertainty magnitudes, probability distributions, covariance, fan-curve uncertainty, variable friction during the loop solve, damper/control behavior, leakage, system effect, acoustics, stall/surge limits, motor/VFD limits, compressibility, or transients. It does not replace manufacturer selection, detailed HVAC design, commissioning, or qualified engineering review.
