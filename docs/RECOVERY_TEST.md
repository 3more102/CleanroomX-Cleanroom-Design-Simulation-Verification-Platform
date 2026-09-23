# Particle recovery-test workflow

CleanroomX v0.12 provides an auditable workflow for measured airborne-particle recovery data with optional deterministic concentration uncertainty.

ISO 14644-3:2019 is the current published ISO test-method standard for cleanrooms and clean zones. CleanroomX does not reproduce its proprietary procedures or acceptance limits. Instead, the software records project-selected targets, measured samples, traceability metadata, supplied measurement uncertainty, and the resulting project criterion status.

Official ISO reference:

- https://www.iso.org/standard/60598.html

## Inputs

A recovery-test record contains:

- particle size;
- target concentration;
- time/concentration samples;
- optional absolute concentration uncertainty for each sample;
- optional maximum recovery time;
- optional instrument identifier;
- optional sample location;
- optional occupancy state;
- optional method/protocol reference.

No target concentration, uncertainty allowance, or maximum time is inferred from an ISO class.

A sample can include:

    {
      "time_minutes": 10.0,
      "concentration_per_m3": 90000.0,
      "concentration_uncertainty_abs": 5000.0
    }

When concentration_uncertainty_abs is omitted it defaults to zero, preserving the earlier exact-value behavior.

## Observed recovery

The nominal result still records the first measured sample at or below the target and the preceding-to-passing sample window. This preserves the original v0.4 trace while avoiding an invented exact crossing time between discrete samples.

For uncertainty-aware qualification, each concentration is treated as the bounded interval:

    max(0, concentration - uncertainty) ... concentration + uncertainty

Each sample is classified as:

- confirmed_at_or_below: the complete interval is at or below the target;
- confirmed_above: the complete interval is above the target;
- overlaps_target: the interval crosses or touches the target without being fully below it.

## Conservative maximum-time decision

If a maximum recovery time is configured:

- pass: at least one sample at or before the maximum time has its complete uncertainty interval at or below the target;
- fail: measurements reach or exceed the maximum time and no sample at or before that time is even possibly at or below the target;
- indeterminate: measurements reach or exceed the maximum time, no sample is confirmed at/below the target by the deadline, but at least one sample at/before the deadline overlaps the target;
- incomplete: measurements stop before the maximum time without a confirmed recovery result.

If no maximum is configured, the result is not_checked.

This is deterministic interval screening. It is not a statistical measurement-uncertainty budget and does not create a conformity decision rule on behalf of the project.

## Log-linear diagnostic

For positive nominal concentration samples, CleanroomX fits:

    ln(C) = intercept + slope * time

When the fitted slope is negative, the diagnostic reports:

    decay rate = -slope
    estimated effective ACH = decay rate * 60

It also reports R² and the fitted target-crossing time.

The fit uses nominal concentration values only. Sample uncertainty is not propagated through the fit, and fitted values remain screening diagnostics rather than qualification acceptance results.

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
- 4: indeterminate because supplied uncertainty overlaps the acceptance boundary.

## References

- ISO 14644-3:2019 — cleanroom and clean-zone test methods.
- JCGM 100:2008 — Guide to the Expression of Uncertainty in Measurement.
- JCGM 106:2012 — role of measurement uncertainty in conformity assessment.
