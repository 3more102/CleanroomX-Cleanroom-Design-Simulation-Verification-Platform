# Fan / loop-network uncertainty

CleanroomX v0.30 adds deterministic bounded uncertainty analysis to the fixed-resistance fan/loop-network workflow.

## Inputs

The nominal fan curve and loop network use the existing fan/loop and loop-network models. Uncertainty is supplied explicitly for:

- fixed pressure, as an absolute interval around its nominal value;
- any named loop-edge quadratic resistance, as an absolute uncertainty in Pa/(m³/s)².

Edges without configured resistance uncertainty remain fixed at nominal resistance. Geometry-derived edges are supported, but their nominal derived resistance is frozen before the explicitly supplied resistance uncertainty is applied. The separate v0.29 variable-friction solver is not iterated inside this uncertainty workflow.

## Corner analysis

For each uncertain input, CleanroomX evaluates the unique lower and upper values. Every resulting corner:

1. rebuilds the loop with that corner's fixed edge resistances;
2. derives the two-terminal equivalent loop resistance from the reference through-flow;
3. intersects the equivalent system curve with the supplied fan curve without extrapolation;
4. re-solves the full loop at the corner operating airflow when an intersection exists.

Zero-width intervals collapse to one value. The default `max_corner_cases` is 256; analyses exceeding that limit are rejected rather than silently truncated.

## Result handling

A `complete` result requires the nominal case and every configured corner to produce a bounded fan/system intersection. CleanroomX reports min/max values across the evaluated corners for:

- operating airflow;
- system pressure;
- equivalent loop resistance.

If any corner has no intersection inside the supplied fan data, the result is `indeterminate`; the complete operating-point envelope and internal branch-flow ranges are withheld.

Internal edge-flow min/max values are reported only when all corners solve, and are explicitly labeled as diagnostic ranges across evaluated corners. They are not claimed as guaranteed extrema over every interior uncertainty combination.

## Traceability

Fan-curve provenance is tracked separately from numerical status. Provenance is also tracked for every nonzero fixed-pressure or edge-resistance uncertainty. Missing provenance does not convert a numerically complete solution into a numerical failure; it is reported as incomplete traceability.

## Run

    cleanroomx-fan-loop-uncertainty examples/fan_loop_uncertainty_demo.json

JSON output:

    cleanroomx-fan-loop-uncertainty examples/fan_loop_uncertainty_demo.json --format json

Markdown report:

    cleanroomx-fan-loop-uncertainty examples/fan_loop_uncertainty_demo.json --output fan-loop-uncertainty-report.md

## Engineering boundary

This is deterministic interval screening from user-supplied bounds. It does not infer uncertainty magnitudes, probability distributions, covariance, fan-curve uncertainty, variable Darcy friction during corner solving, damper/control behavior, leakage, system effect, acoustics, stall/surge limits, motor/VFD limits, compressibility, or transients. It does not replace manufacturer selection, detailed HVAC design, commissioning, or qualified engineering review.
