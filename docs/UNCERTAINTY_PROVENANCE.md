# Uncertainty and provenance workflow

CleanroomX v0.5 adds a conservative interval-analysis foundation for engineering inputs together with explicit source provenance.

## Scope

The foundation covers room dimensions, supply airflow, derived room volume, derived supply ACH, and a project-configured minimum ACH requirement. v0.7 extends the same conservative interval approach to observed room differential pressure and room-to-room pressure-cascade verification.

Each numeric input carries:

- nominal value;
- absolute uncertainty bound;
- fixed engineering unit;
- optional source type and source name;
- optional document/reference identifier;
- optional revision and date;
- optional uncertainty-basis note;
- optional free-form notes.

No uncertainty is invented by CleanroomX. If no bound is supplied, the input is treated as exact for this workflow.

## Conservative interval propagation

For a positive input x with supplied absolute bound u:

    x_low = x - u
    x_high = x + u

For positive room dimensions:

    V_low = L_low * W_low * H_low
    V_high = L_high * W_high * H_high

For supply airflow Q and volume V:

    ACH_low = Q_low / V_high
    ACH_high = Q_high / V_low

This is deterministic worst-case interval arithmetic. It does not assume a probability distribution, confidence level, independence model, or coverage factor.

## Requirement result

For a configured minimum ACH:

- pass: the complete ACH interval is at or above the minimum;
- fail: the complete ACH interval is below the minimum;
- indeterminate: the minimum lies inside the interval;
- not_checked: no minimum was configured.

The indeterminate state is intentional. It prevents a nominal value from being reported as a robust pass when plausible input bounds cross the project requirement.

## Pressure uncertainty extension

A room may provide an absolute pressure uncertainty bound:

    observed_pressure_pa = p
    observed_pressure_uncertainty_pa = u_p

CleanroomX evaluates the pressure interval as:

    p_low = p - u_p
    p_high = p + u_p

For a configured minimum room pressure, the result is pass only when the complete interval is at or above the minimum, fail only when the complete interval is below it, and indeterminate when the minimum lies inside the interval.

For a cascade from a higher-pressure room H to a lower-pressure room L:

    delta_p = p_H - p_L
    u_delta = u_H + u_L
    delta_low = delta_p - u_delta
    delta_high = delta_p + u_delta

The summed absolute bound is deterministic worst-case interval propagation. It is not root-sum-square statistical uncertainty and does not assume independent random errors.

## Provenance completeness

The report lists every analyzed input and its source metadata. Provenance completeness is reported separately from engineering acceptance. Missing provenance does not silently change a numerical result.

## Engineering boundary

This workflow is a screening and traceability tool. It is not a statistical measurement-uncertainty budget, does not claim conformity with a particular metrology standard, and does not replace calibration records, the project validation plan, qualification procedures, or qualified engineering judgment.

## CLI

    cleanroomx-uncertainty examples/uncertainty_room_demo.json

JSON output:

    cleanroomx-uncertainty examples/uncertainty_room_demo.json --format json

Write a Markdown report:

    cleanroomx-uncertainty examples/uncertainty_room_demo.json --output uncertainty-report.md

Exit codes:

- 0: pass or not-checked only;
- 2: at least one configured requirement robustly fails;
- 3: no robust failure, but at least one configured requirement is indeterminate.
