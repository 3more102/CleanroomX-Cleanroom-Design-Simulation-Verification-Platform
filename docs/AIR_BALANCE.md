# Room air-balance model

CleanroomX v0.3 adds an explicit steady-state volumetric air-balance check to the preliminary HVAC workflow.

## Inputs

Each HVAC room may define an optional `air_balance` block with:

- return air;
- exhaust air;
- transfer air entering the room;
- transfer air leaving the room;
- leakage/infiltration entering the room;
- leakage/exfiltration leaving the room;
- an explicit balance tolerance.

All values are in m³/h.

The supply used by the balance is the room's **governing supply airflow** calculated by the HVAC workflow. Outdoor/makeup air is a component of that supply, so it is not added again in the room balance.

## Equations

Mechanical surplus:

    mechanical_surplus = supply - return - exhaust

Passive net outflow:

    passive_net_outflow =
        transfer_out + leakage_out - transfer_in - leakage_in

Balance residual:

    residual = mechanical_surplus - passive_net_outflow

Equivalently:

    residual =
        supply + transfer_in + leakage_in
        - return - exhaust - transfer_out - leakage_out

A room is reported as `balanced` when the absolute residual is less than or equal to the user-entered tolerance.

If residual is positive, the model reports how much additional unmodeled outflow would be required for steady-state closure. If residual is negative, it reports the additional unmodeled inflow required.

## Important engineering boundary

A supply/return surplus does **not** by itself determine a room pressure differential. Actual pressure depends on leakage areas, door states, transfer paths, envelope characteristics, controls, wind/stack effects, and other network behavior.

CleanroomX therefore keeps pressure verification separate from volumetric balance. This module is a transparent accounting check, not a pressure-network solver, CFD calculation, TAB procedure, or certification method.
