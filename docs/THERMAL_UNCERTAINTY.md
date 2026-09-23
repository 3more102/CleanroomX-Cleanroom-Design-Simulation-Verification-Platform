# Thermal uncertainty workflow

The CleanroomX thermal/HVAC uncertainty workflow can reuse the v0.15 psychrometric uncertainty model for room and outdoor air-state bounds.

## Scope

The workflow propagates user-supplied absolute bounds for:

- cleanroom design airflow;
- internal sensible load;
- internal latent load;
- makeup-air airflow;
- optional supply-air temperature;
- optional room-air dry-bulb temperature, relative humidity, and pressure;
- optional outdoor-air dry-bulb temperature, relative humidity, and pressure.

Capacity margin remains a fixed project input. No uncertainty bound is invented by CleanroomX.

Legacy fixed air-state JSON remains supported. To make an air-state component uncertain, provide the same `value`, `uncertainty_abs`, and optional `provenance` object used by the standalone psychrometric uncertainty workflow. Mixed fixed/uncertain components are allowed.

## Shared psychrometric model

Thermal uncertainty uses the same `UncertainAirState` model and corner generation as `cleanroomx-psychrometric-uncertainty`.

For an uncertain air state, every unique endpoint combination of dry-bulb temperature, relative humidity, and pressure is evaluated. With all three components uncertain, that is eight corners.

The thermal report includes the same bounded psychrometric properties:

- vapor pressure;
- humidity ratio;
- moist-air enthalpy;
- moist-air specific volume;
- dew-point temperature;
- moist-air specific heat.

This avoids maintaining a second air-state uncertainty implementation and keeps standalone and thermal calculations on the same validated input domain.

## Load propagation

Internal load bounds are additive:

    Q_internal,low = Q_sensible,low + Q_latent,low
    Q_internal,high = Q_sensible,high + Q_latent,high

Makeup-air total load is evaluated across the Cartesian product of:

- makeup-airflow lower/upper bounds;
- all room-air state corners;
- all outdoor-air state corners.

For each combination:

    m_da = V_dot / v_outdoor
    Q_makeup = m_da * (h_outdoor - h_room)

The minimum and maximum evaluated values form the conservative makeup-air load interval.

With fixed room/outdoor states, this reduces to the previous fixed-state behavior.

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

Sensible-load airflow is evaluated across sensible-load bounds, supply-air-temperature bounds, and every room-air state corner. For positive sensible load, the complete supply-air-temperature interval must remain below the lowest room dry-bulb temperature.

The governing airflow lower and upper bounds are the maximum of the corresponding candidate lower and upper bounds. The nominal governing basis is reported separately.

## Traceability

Every uncertain numeric input may carry the existing CleanroomX provenance record: source type/name, reference, revision, date, uncertainty basis, and notes.

Explicitly uncertain or provenance-bearing psychrometric components are included in the thermal traceability table. Missing provenance remains separate from capacity acceptance.

## JSON example

    "room_air": {
      "dry_bulb_c": {
        "value": 22.0,
        "uncertainty_abs": 0.5
      },
      "relative_humidity_percent": {
        "value": 45.0,
        "uncertainty_abs": 3.0
      },
      "pressure_kpa": 101.325
    }

A scalar component remains fixed and backward compatible.

## Engineering boundary

This is deterministic endpoint-interval screening. It is not a statistical measurement-uncertainty budget and does not model correlation between uncertain inputs. It is also not hourly weather/load simulation, coil selection, equipment derating, or transient HVAC simulation.

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
