# Airflow balance and fan-sizing model

CleanroomX v0.3 adds transparent steady-state airflow-balance checks and preliminary supply-fan sizing. The model deliberately requires project-specific airflow targets, pressure drops, and efficiencies instead of inventing values from an ISO class.

## Room airflow balance

For each room the HVAC module uses the governing supply airflow already selected by the cleanroom/thermal calculation and accepts explicit:

- return airflow;
- exhaust airflow;
- transfer airflow into the room;
- transfer airflow out of the room;
- minimum required net airflow surplus.

The steady-state net surplus is:

    net surplus = supply + transfer in - return - exhaust - transfer out

The reported margin is:

    surplus margin = net surplus - minimum required surplus

A positive net surplus represents airflow available for exfiltration or another unmodeled outflow path at steady state. A negative value means infiltration or another unmodeled inflow would be required to close the mass balance.

This is an airflow calculation only. CleanroomX does not convert airflow surplus into room differential pressure because that requires a leakage-path/door/transfer model or measured flow-pressure relationship.

## Filter pressure drop

An optional pressure drop can be supplied for the project filter/FFU definition. It is treated as one terminal pressure-drop component in the supply-fan duty calculation. Parallel terminal filters increase available airflow capacity by unit count; their pressure drops are not summed in series.

## Supply-fan duty

If a fan system is configured, CleanroomX sums these explicit pressure-drop components:

    total static = duct + coil + terminal filter + other

Air power is:

    air power = volumetric airflow × total static pressure

with airflow converted to m³/s. Shaft power and estimated electrical input are then calculated from entered fan and motor efficiencies:

    shaft power = air power / fan efficiency
    electrical input = shaft power / motor efficiency

## Limits

This model is for preliminary engineering screening. It does not infer duct geometry, fittings, system effect, velocity pressure, dirty-filter allowance, VFD/control losses, altitude correction, redundancy, sound limits, fan curves, operating point, leakage coefficients, or final equipment selection.

Use project specifications, licensed standards, local regulations, manufacturer data, and qualified engineering review for real designs.
