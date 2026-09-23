# Measured recovery-test workflow

CleanroomX v0.4 adds a workflow for analyzing an explicit time series of measured airborne-particle concentrations after a recovery challenge.

The workflow is deliberately requirement-driven. It does not invent an acceptance time or claim that a fitted decay curve is a cleanroom certification result.

## Input

A recovery-test JSON file contains:

- a test name;
- a user-selected target concentration;
- at least two measured samples;
- an optional maximum allowed recovery time;
- optional design ACH and removal efficiency for comparison with the existing screening model.

The first sample must be at time 0. Sample times must be strictly increasing. Concentrations must be positive because the regression is performed on the natural logarithm of concentration.

## Observed recovery time

CleanroomX finds the first measured interval that crosses the configured target. The crossing time is interpolated between the two bracketing samples on a log-concentration scale.

If the target is never reached within the supplied samples, the observed recovery time is reported as null.

If a maximum recovery time is configured, the result passes only when the target is reached at or before that time.

## Descriptive fit

The workflow performs an ordinary least-squares fit of:

    ln(C) = intercept + slope × time

and reports:

- the fitted log-concentration slope;
- effective removal rate = -slope;
- effective removal rate in 1/h;
- fitted concentration half-life when the fitted removal rate is positive;
- R² on ln(concentration).

Measured concentrations are not required to decrease monotonically, so the fit can expose noisy or poorly exponential data instead of rejecting it.

## Screening-model comparison

When design ACH is provided, CleanroomX also calculates the existing well-mixed first-order screening-model recovery time using the explicit removal efficiency. The report shows observed minus predicted time.

This comparison is diagnostic only. It does not establish causality or replace a validated recovery-test procedure.

## CLI

JSON output:

    cleanroomx recovery-test examples/recovery_test_demo.json

Markdown output:

    cleanroomx recovery-test examples/recovery_test_demo.json --format markdown

Write the report to a file:

    cleanroomx recovery-test examples/recovery_test_demo.json --format markdown --output recovery-report.md

A configured maximum recovery-time failure returns exit code 2, which makes the workflow usable in automated project checks.

## Engineering boundary

The implementation does not define sampling locations, challenge generation, instrument specifications, counting intervals, background correction, statistical confidence, certification method, or acceptance limits. Use the applicable licensed standard, client specification, regulator requirements, validated test method, and qualified cleanroom professional for real acceptance testing.
