# Particle recovery-test workflow

CleanroomX v0.14 extends the measured airborne-particle recovery workflow with deterministic concentration-uncertainty intervals while preserving the original v0.4 behavior when no uncertainty is supplied.

ISO 14644-3:2019 is the current published ISO test-method standard for cleanrooms and clean zones. CleanroomX does not reproduce proprietary procedures or acceptance limits. The software evaluates only project-supplied targets, measured samples, uncertainty values, traceability metadata, and optional maximum recovery time.

Official ISO reference:

- https://www.iso.org/standard/60598.html

## Inputs

A recovery-test record contains:

- particle size;
- target concentration;
- time/concentration samples;
- optional absolute concentration uncertainty on each sample;
- optional maximum recovery time;
- optional instrument identifier;
- optional sample location;
- optional occupancy state;
- optional method/protocol reference;
- optional uncertainty reference or basis.

A sample without `concentration_uncertainty_abs` is treated as zero uncertainty for backward compatibility. No target concentration, uncertainty value, or maximum time is inferred from an ISO class.

## Deterministic uncertainty interval

For each measured sample:

    lower = max(0, concentration - absolute_uncertainty)
    upper = concentration + absolute_uncertainty

The target relation is:

- `confirmed_at_or_below`: the complete interval is at or below the target;
- `confirmed_above`: the complete interval is above the target;
- `overlaps_target`: the interval crosses the target and the sample alone cannot support a robust pass/fail conclusion.

This is deterministic interval screening. It is not a statistical uncertainty budget and does not invent coverage factors, distributions, calibration uncertainty, or conformity rules.

## Recovery acceptance

The legacy nominal recovery time remains available as the first nominal sample at or below the target. v0.14 also reports the first sample that could be at/below the target and the first sample whose complete interval is confirmed at/below the target.

If a maximum recovery time is configured:

- `pass`: a confirmed at/below-target sample occurs at or before the maximum time;
- `indeterminate`: no confirmed sample occurs within the maximum time, but at least one sample at or before that time overlaps the target;
- `fail`: measurements reach or exceed the maximum time and no sample at or before it could be at/below the target;
- `incomplete`: measurements stop before the maximum time and no sample could be at/below the target.

If no maximum is configured, the criterion result is `not_checked`.

## Log-linear diagnostic

For positive nominal concentration samples, CleanroomX also fits:

    ln(C) = intercept + slope * time

When the fitted slope is negative, the diagnostic reports:

    decay rate = -slope
    estimated effective ACH = decay rate * 60

It also reports R² and the fitted target-crossing time. The fit uses nominal concentrations only and remains a screening diagnostic; it is not used for acceptance.

## CLI

    cleanroomx-recovery-test examples/recovery_test_demo.json

JSON output:

    cleanroomx-recovery-test examples/recovery_test_demo.json --format json

Write a Markdown report:

    cleanroomx-recovery-test examples/recovery_test_demo.json --output recovery-report.md

Exit codes:

- 0: pass or no maximum-time criterion configured;
- 2: fail;
- 3: incomplete test;
- 4: indeterminate because supplied concentration uncertainty overlaps the target.

The integrated engineering dossier preserves `indeterminate` recovery results as attention items.
