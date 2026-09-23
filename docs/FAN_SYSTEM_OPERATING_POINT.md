# Fan/system operating-point solver

CleanroomX adds a bounded steady-state fan/system operating-point calculation using explicit fan performance points and an explicit quadratic system curve.

## Fan curve

The fan curve is supplied as two or more pressure/airflow points:

- airflow must be strictly increasing;
- pressure must be non-increasing with airflow;
- all values must be finite and non-negative.

CleanroomX uses piecewise-linear interpolation **only between supplied fan-curve points**. It does not extrapolate beyond the lowest or highest supplied airflow.

## System curve

The modeled system pressure is:

    delta_p_system = delta_p_fixed + R * Q^2

where:

- `delta_p_fixed` is an explicit fixed pressure component in Pa;
- `R` is an explicit constant resistance in Pa/(m3/s)^2;
- `Q` is airflow in m3/s.

The fixed component can represent pressure terms that the project deliberately treats as flow-independent for this screening calculation. The quadratic term represents a fixed-resistance approximation.

## Operating point

Within each supplied fan-curve segment, CleanroomX compares interpolated fan pressure with system pressure and solves the crossing. A solved result reports:

- operating airflow;
- fan pressure;
- system pressure;
- fan-minus-system pressure residual;
- air power `Q * delta_p`;
- the fan-curve segment used for interpolation.

If the curves do not intersect inside the supplied fan data, the solver returns `no_intersection_in_supplied_range` rather than extrapolating.

## JSON input

    {
      "name": "Supply fan operating-point demo",
      "fan_curve": {
        "name": "Example manufacturer fan curve",
        "points": [
          {"airflow_m3_h": 0.0, "pressure_pa": 600.0},
          {"airflow_m3_h": 3000.0, "pressure_pa": 500.0},
          {"airflow_m3_h": 6000.0, "pressure_pa": 300.0},
          {"airflow_m3_h": 8000.0, "pressure_pa": 100.0}
        ]
      },
      "system_curve": {
        "name": "Example duct system",
        "fixed_pressure_pa": 80.0,
        "resistance_pa_per_m3_s_squared": 100.0
      }
    }

Run:

    cleanroomx-fan-curve examples/fan_operating_point_demo.json

JSON output:

    cleanroomx-fan-curve examples/fan_operating_point_demo.json --format json

## Engineering boundary

This is a screening calculation for a single supplied fan curve and a fixed quadratic system model. It does not infer a manufacturer curve, scale curves with fan laws, model variable friction factor, determine system effect, evaluate stall/surge boundaries, model VFD/control behavior, solve parallel fans, or replace manufacturer selection and qualified HVAC engineering review.

The reported air power is fluid power only. It is not shaft power or electrical input power unless separately supported by efficiency data.

## References

ASHRAE states that fan selection requires matching fan pressure capability with system pressure loss at the design condition, and its fan guidance discusses the selected operating point on the fan/system curves:

https://handbook.ashrae.org/Handbooks/S24/SI/S24_Ch21/S24_Ch21_si.aspx

The U.S. Department of Energy fan sourcebook describes fan performance curves as developed pressure and required power over fan-generated airflow:

https://www.energy.gov/sites/default/files/2014/05/f16/fan_sourcebook.pdf
