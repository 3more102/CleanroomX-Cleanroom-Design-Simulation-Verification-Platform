# Fan/system operating-point solver

CleanroomX v0.10 adds a bounded steady-state operating-point solver for an explicit fan static-pressure curve and an explicit quadratic system curve.

## Fan curve

The fan curve is entered as two or more airflow/static-pressure points. Airflow must increase strictly and static pressure must be non-increasing. CleanroomX uses piecewise-linear interpolation only between supplied points.

It does not fit or invent a manufacturer curve and does not extrapolate beyond the supplied airflow range.

## System curve

The system curve is:

    delta_p_system = P_fixed + R * Q^2

where P_fixed is an explicit non-negative fixed pressure component in Pa, R is an explicit positive resistance in Pa/(m3/s)^2, and Q is airflow in m3/s.

The solver intersects each linear fan segment analytically with the quadratic system curve and reports the unique in-range operating point. The result includes fan/system pressure residual, air power, the interpolated fan segment, and boundary pressure margins.

If no in-range intersection exists, the result is no_intersection; CleanroomX does not silently extend the fan data.

## CLI

    cleanroomx-fan-curve examples/fan_curve_demo.json

JSON output:

    cleanroomx-fan-curve examples/fan_curve_demo.json --format json

Write Markdown:

    cleanroomx-fan-curve examples/fan_curve_demo.json --output fan-operating-point.md

The CLI returns exit code 2 when no in-range operating point exists.

## Engineering boundary

This is a bounded steady-state screening solver. Fan points, fixed pressure, and quadratic resistance are explicit project/manufacturer inputs. The model does not infer fan speed laws, efficiency curves, shaft or electrical input, variable friction factor with Reynolds number, density correction, system effect, dampers/controllers, leakage, multiple interacting fans, stall/surge behavior, or transient response.

Use current manufacturer certified performance data, project design conditions, applicable standards, and qualified HVAC engineering review for real fan selection.
