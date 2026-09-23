# Thermal uncertainty workflow

CleanroomX v0.10 extends deterministic uncertainty screening into preliminary thermal/HVAC sizing.

## Scope

The workflow propagates user-supplied absolute bounds for:

- cleanroom design airflow;
- internal sensible load;
- internal latent load;
- makeup-air airflow;
- optional supply-air temperature.

Room and outdoor psychrometric states are held fixed. Capacity margin is also a fixed project input.

No uncertainty bound is invented by CleanroomX.

## Load propagation

Internal load bounds are additive:

    Q_internal,low = Q_sensible,low + Q_latent,low
    Q_internal,high = Q_sensible,high + Q_latent,high

For fixed room/outdoor states, the makeup-air enthalpy load is linear in makeup airflow. CleanroomX calculates the fixed load-per-flow coefficient from the outdoor dry-air specific volume and the outdoor-to-room moist-air enthalpy difference, then propagates the configured makeup-airflow interval.

The room-plus-makeup interval is the sum of the internal and makeup-air load intervals.

## Cooling and heating requirements

A configured capacity margin is applied to the complete net-load interval.

Cooling requirement:

    Q_cool = max(Q_net, 0) * margin_multiplier

Heating requirement:

    Q_heat = max(-Q_net, 0) * margin_multiplier

If an available cooling or heating capacity is supplied, the decision is:

- pass when the available capacity covers the complete requirement interval;
- fail when the complete requirement interval is above the available capacity;
- indeterminate when the available capacity lies inside the requirement interval;
- not_checked when no available capacity is configured.

## Airflow propagation

The workflow compares conservative intervals for:

- cleanroom airflow;
- makeup airflow;
- sensible-load airflow when a supply-air temperature is configured.

For positive sensible load, the complete supply-air-temperature interval must remain below the fixed room dry-bulb temperature.

The governing airflow lower and upper bounds are the maximum of the corresponding candidate lower and upper bounds. The nominal governing basis is reported separately.

## Traceability

Every uncertain numeric input may carry the existing CleanroomX provenance record: source type/name, reference, revision, date, uncertainty basis, and notes. Missing provenance is reported separately from capacity acceptance.

## Engineering boundary

This is deterministic interval screening. It is not a statistical measurement-uncertainty budget, hourly weather/load simulation, psychrometric-state uncertainty model, coil selection, equipment derating model, or transient HVAC simulation.

Use project load criteria, current weather/design data, manufacturer capacity data, applicable standards, and qualified HVAC/cleanroom engineering review for real designs.

## CLI

    cleanroomx-thermal-uncertainty examples/thermal_uncertainty_demo.json

JSON output:

    cleanroomx-thermal-uncertainty examples/thermal_uncertainty_demo.json --format json

Write a Markdown report:

    cleanroomx-thermal-uncertainty examples/thermal_uncertainty_demo.json --output thermal-uncertainty-report.md

Exit codes:

- 0: pass or no configured equipment-capacity check;
- 2: fail;
- 3: indeterminate.
