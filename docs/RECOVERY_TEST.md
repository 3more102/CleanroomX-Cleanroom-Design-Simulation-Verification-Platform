# Particle recovery-test workflow

CleanroomX v0.4 adds an auditable workflow for measured airborne-particle recovery data.

ISO 14644-3:2019 is the current published ISO test-method standard for cleanrooms and clean zones. CleanroomX does not reproduce its proprietary procedures or acceptance limits. Instead, the software records project-selected targets, measured samples, traceability metadata, and the resulting project criterion status.

Official ISO reference:

- https://www.iso.org/standard/60598.html

## Inputs

A recovery-test record contains:

- particle size;
- target concentration;
- time/concentration samples;
- optional maximum recovery time;
- optional instrument identifier;
- optional sample location;
- optional occupancy state;
- optional method/protocol reference.

No target concentration or maximum time is inferred from an ISO class.

## Observed recovery

The acceptance result uses measured samples directly.

The first sample at or below the target is reported as the observed recovery time. The preceding sample and first passing sample form a recovery-time window. This avoids pretending that the exact crossing time is known between discrete measurements.

If a maximum recovery time is configured:

- `pass`: the first passing sample occurs within the maximum time;
- `fail`: the first passing sample occurs after the maximum, or measurements continue beyond the maximum while remaining above target;
- `incomplete`: measurements stop before the maximum while still above target.

If no maximum is configured, the result is `not_checked`.

## Log-linear diagnostic

For positive concentration samples, CleanroomX also fits:

    ln(C) = intercept + slope * time

When the fitted slope is negative, the diagnostic reports:

    decay rate = -slope
    estimated effective ACH = decay rate * 60

It also reports R² and the fitted target-crossing time.

These fitted values are screening diagnostics only. They do not replace the measured acceptance result or the project qualification method.

## CLI

    cleanroomx-recovery-test examples/recovery_test_demo.json

JSON output:

    cleanroomx-recovery-test examples/recovery_test_demo.json --format json

Write a Markdown report:

    cleanroomx-recovery-test examples/recovery_test_demo.json --output recovery-report.md

Exit codes:

- 0: pass or no maximum-time criterion configured;
- 2: fail;
- 3: incomplete test.


## Uncertainty-aware companion workflow

CleanroomX v0.14 adds a separate conservative interval workflow for measured recovery samples with user-supplied absolute concentration uncertainty. It preserves `indeterminate` when the concentration interval overlaps the project target rather than forcing a nominal pass/fail decision.

See `docs/RECOVERY_UNCERTAINTY.md` and run:

    cleanroomx-recovery-uncertainty examples/recovery_uncertainty_demo.json
