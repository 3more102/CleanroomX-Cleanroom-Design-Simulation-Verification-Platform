# Recovery concentration uncertainty

CleanroomX v0.8 extends measured particle-recovery qualification with user-supplied absolute uncertainty for each concentration sample.

## Input

Each recovery sample may include:

    concentration_uncertainty_per_m3

If omitted, the value defaults to zero and the existing nominal workflow is preserved.

For concentration C with absolute uncertainty u, CleanroomX evaluates the deterministic interval:

    [C - u, C + u]

The lower bound must remain non-negative.

## Target relation

For a configured target concentration T, each sample is classified as:

- **at_or_below** when C + u <= T;
- **above** when C - u > T;
- **indeterminate** when the interval overlaps T.

This prevents an uncertainty-overlapping sample from being treated as a definite recovery event.

## Maximum recovery-time decision

When a maximum recovery time is configured:

- **pass** requires a definitely recovered sample within the allowed time;
- **fail** is reported when no measured sample is even possibly at/below the target within the allowed time and the test has progressed far enough to decide;
- **indeterminate** is reported when an uncertainty-overlapping sample within the allowed time could represent recovery but definite recovery is demonstrated only later or not at all;
- **incomplete** remains reserved for tests that end before the configured maximum time without enough evidence to decide.

The report includes both the first possible recovery sample and the first definite recovery sample.

## Diagnostic fit

The existing log-linear fit and effective-ACH diagnostic continue to use nominal concentration values. Concentration uncertainty does not imply a probability distribution and is not converted into statistical fit weights.

## Scope

This is deterministic interval screening. CleanroomX does not derive instrument uncertainty, calibration uncertainty, confidence level, coverage factor, correlation, or a regulatory conformity decision rule. Use the applicable qualification protocol, calibration records, project requirements, standards, and qualified engineering judgment for real acceptance decisions.
