# Recovery acceptance with concentration uncertainty

CleanroomX v0.14 adds a deterministic uncertainty-aware
acceptance workflow for measured particle-recovery samples.

## Scope

Each measured concentration is represented by a nominal value and
a user-supplied absolute uncertainty bound. CleanroomX forms the
conservative interval

`[max(0, C - U), C + U]`

and compares the complete interval with the project-supplied target
concentration.

A sample is:

- `at_or_below_target` when its upper bound is at or below the target;
- `above_target` when its lower bound is above the target;
- `indeterminate` when its interval overlaps the target.

For a configured maximum recovery time, the result is `pass` only
when at least one sample at or before the time limit is wholly at or
below the target. An overlapping sample at or before the limit yields
`indeterminate`. If measurements reach the time limit and all samples
at or before it are definitely above target, the result is `fail`.
If the test ends early, the result is `incomplete`.

## Engineering boundary

This is deterministic interval screening, not a statistical
measurement-uncertainty budget. CleanroomX does not invent uncertainty
values, does not infer an exact target crossing between samples, does
not assume a probability distribution, and does not embed ISO class
limits or a universal recovery-time requirement.

Use the uncertainty statement and decision rule required by the
applicable calibration record, project qualification protocol, client
specification, regulator, or accredited laboratory procedure.

## CLI

```text
cleanroomx-recovery-uncertainty examples/recovery_uncertainty_demo.json
cleanroomx-recovery-uncertainty examples/recovery_uncertainty_demo.json --format json
cleanroomx-recovery-uncertainty examples/recovery_uncertainty_demo.json --output recovery-uncertainty-report.md
```

Exit codes are `0` for pass/not-checked, `2` for fail, `3` for
incomplete, and `4` for indeterminate.
