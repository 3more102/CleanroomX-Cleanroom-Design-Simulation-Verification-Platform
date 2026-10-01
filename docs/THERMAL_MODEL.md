# Preliminary thermal / HVAC model

CleanroomX v0.2 includes an isolated HVAC module for early design studies. It is additive to the existing room, particle, and pressure-verification core.

## Inputs

Each HVAC room can define:

- the independently selected cleanroom supply airflow;
- room dry-bulb temperature, relative humidity, and atmospheric pressure;
- outdoor dry-bulb temperature, relative humidity, and atmospheric pressure;
- makeup/outdoor airflow;
- people sensible and latent gains;
- lighting, equipment, envelope, and other sensible gains;
- process and other latent gains;
- supply-air temperature;
- an explicit user-selected capacity margin;
- an optional FFU/filter-unit airflow and design-utilization value.

No occupancy gains, weather conditions, ventilation quantity, ISO-to-ACH mapping, or sizing margin is silently assumed.

## Psychrometrics

Saturation vapor pressure is phase-aware and follows the reference formulations used by the 2025 ASHRAE Handbook—Fundamentals, Chapter 1:

- below 0 °C: IAPWS R14-08(2011) ice-Ih sublimation-pressure correlation;
- at and above 0 °C: IAPWS-IF97 Region 4 liquid-water saturation-pressure equation.

The `AirState` model remains intentionally limited to -45 to 60 °C. Dew point is solved deterministically by inverting one continuous phase branch of the same saturation-pressure model, rather than mixing a separate Magnus approximation into the result. Because the ASHRAE convention switches from the ice-Ih curve below 0 °C to the liquid-water curve at 0 °C, the two branch values leave a very narrow vapor-pressure interval with no mathematical root in the implemented piecewise function; CleanroomX reports that interval explicitly as indeterminate instead of returning a false bisection convergence. If the implied dew point is below -100 °C, CleanroomX also fails explicitly because that is outside the supported inversion range.

The humidity-ratio molecular-mass coefficient is 0.621945. Approximate moist-air enthalpy is:

    h = 1.006 t + W (2501 + 1.86 t) kJ/kg dry air

## Airflow selection

CleanroomX compares three explicit airflow drivers when available:

1. independently entered cleanroom airflow;
2. required makeup airflow;
3. airflow required to remove entered internal sensible load at the entered supply-air temperature.

The largest becomes the preliminary governing airflow. CleanroomX keeps the unrounded calculated airflow for downstream engineering decisions and rounds only when formatting reported values. If an FFU/filter-unit model is supplied, the program rounds up the unit count from that full-precision governing airflow using its rated airflow multiplied by the entered design-utilization factor; display rounding cannot reduce the required unit count.

## Capacity

Internal sensible and latent loads are summed directly. Makeup-air total load is calculated from dry-air mass flow and the outdoor-to-room enthalpy difference. The explicit capacity margin is then applied to the positive cooling or heating load.

## Limits

This is not a final coil-selection, CFD, certification, or code-compliance calculation. The current model does not include detailed solar/envelope conduction, fan heat, duct heat gain/loss, coil bypass factor or ADP, humidification/dehumidification equipment selection, diversity schedules, heat recovery, weather databases, or transient loads.


## v0.10 uncertainty extension

For deterministic interval propagation of explicit thermal loads, airflow inputs, supply-air temperature, and optional available cooling/heating capacity checks, see `docs/THERMAL_UNCERTAINTY.md`.

The v0.10 uncertainty workflow holds room/outdoor psychrometric states fixed; it does not turn the preliminary thermal model into an hourly load or probabilistic uncertainty simulation.


## Numerical integrity

All user-supplied thermal inputs are finite-validated by the model layer. The
thermal calculation also finite-validates derived loads, makeup-air mass flow,
capacity sizing, and sensible-load airflow before returning results. If an
extreme but individually finite input set would overflow floating-point
arithmetic, CleanroomX raises a descriptive `ValueError` rather than emitting
`NaN` or `Infinity` into an engineering result or serialized report. This
guard does not change the equations or normal-range results.
