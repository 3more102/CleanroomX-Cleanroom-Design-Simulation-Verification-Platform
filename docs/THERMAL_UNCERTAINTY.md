# Thermal input uncertainty screening

CleanroomX v0.8 adds a bounded-input screening workflow around the existing preliminary thermal/HVAC model.

## Purpose

The workflow evaluates combinations of user-supplied lower and upper input endpoints for:

- independently selected cleanroom supply airflow;
- room dry-bulb temperature, relative humidity, and atmospheric pressure;
- outdoor dry-bulb temperature, relative humidity, and atmospheric pressure;
- makeup/outdoor airflow;
- supply-air temperature.

Existing internal sensible/latent load inputs and the explicit capacity margin remain deterministic in this workflow.

## Method

For every input with an absolute uncertainty bound `u`, CleanroomX evaluates the two endpoints:

    x_low = x - u
    x_high = x + u

Inputs with zero uncertainty contribute only their nominal value. The workflow evaluates the Cartesian product of the resulting endpoints and reuses the normal CleanroomX thermal calculation for every scenario.

Reported envelopes include:

- preliminary cooling capacity;
- preliminary heating capacity;
- governing supply airflow;
- makeup-air total load;
- net room-plus-makeup load;
- internal sensible-load airflow when that calculation is defined.

The nominal result is calculated separately at the supplied nominal inputs.

## Important interpretation limit

Psychrometric and HVAC relationships are nonlinear. Evaluating all input endpoints is therefore an **endpoint-scenario envelope**, not a proof that the reported minima and maxima are the mathematical global extrema everywhere inside the continuous uncertainty box.

The result is also not a statistical uncertainty budget and does not imply any confidence level or coverage probability.

Use this workflow for sensitivity screening and traceability. A project-specific uncertainty method, validated numerical interval method, Monte Carlo method, calibration program, or regulated conformity-assessment procedure may be required for final engineering decisions.

## Input validity

CleanroomX rejects uncertainty intervals that would leave the supported psychrometric domain:

- dry-bulb temperature must remain within -45 to 60 °C;
- relative humidity must remain above 0% and at or below 100%;
- atmospheric pressure must remain positive;
- cleanroom airflow must remain positive;
- makeup airflow must remain non-negative.

An outdoor air state is required whenever the makeup-air uncertainty interval can be above zero.

## CLI

    cleanroomx-thermal-uncertainty examples/thermal_uncertainty_demo.json

JSON output:

    cleanroomx-thermal-uncertainty examples/thermal_uncertainty_demo.json --format json

Write a Markdown report:

    cleanroomx-thermal-uncertainty examples/thermal_uncertainty_demo.json --output thermal-uncertainty-report.md

## Traceability

Each uncertain value can carry the same provenance fields already used by CleanroomX:

- source type;
- source name;
- reference;
- revision;
- date;
- uncertainty basis;
- notes.

Missing provenance is reported separately and does not silently change the numerical envelope.
