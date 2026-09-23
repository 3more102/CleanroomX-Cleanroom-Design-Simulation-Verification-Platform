# Airflow balance and pressurization screening

CleanroomX v0.3 adds a room/facility airflow-balance engine for early design and verification work.

## Model

For each room, CleanroomX evaluates:

    entering = supply + transfer_in
    leaving  = return + exhaust + transfer_out
    net_offset = entering - leaving

A positive net offset is reported as a **positive pressurization tendency**, a negative offset as a **negative pressurization tendency**, and zero as neutral.

Room-to-room transfer flows are entered once as directed links. Because an internal transfer leaves one room and enters another, all internal transfers cancel when the full facility is summed. CleanroomX reports a conservation error so regressions or malformed calculations are visible.

## Requirement-driven checks

A room may optionally provide:

- `min_net_offset_m3_h`
- `max_net_offset_m3_h`

These are project requirements, not built-in cleanroom-standard limits. A configured failure makes `cleanroomx-balance` return exit code 2.

This allows positive rooms, negative rooms, or bounded offsets to be represented without embedding an ISO class-to-airflow rule.

## Engineering boundary

Airflow offset is not converted into differential pressure. Actual pressure depends on envelope leakage, doors/openings, adjacent spaces, controls, wind/building effects, and commissioning.

ASHRAE's Clean Spaces guidance describes positive pressurization as entering supply airflow exceeding return/exhaust airflow, and negative pressurization as the reverse. It also notes that multi-space cleanroom pressurization is coupled through leakage between adjacent spaces and must be commissioned and controlled as a system.

Reference:

- ASHRAE Handbook — Clean Spaces: https://handbook.ashrae.org/Handbooks/A23/SI/a23_ch19/a23_ch19_si.aspx

## CLI

    cleanroomx-balance examples/airflow_balance_demo.json

JSON output:

    cleanroomx-balance examples/airflow_balance_demo.json --format json

Write a Markdown report:

    cleanroomx-balance examples/airflow_balance_demo.json --output airflow-balance.md
