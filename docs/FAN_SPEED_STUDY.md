# Fan-speed affinity-law operating-point study

CleanroomX v0.19 adds a bounded fan-speed sweep for a supplied reference fan curve and an explicit fixed-plus-quadratic system curve.

## Method

For each user-supplied speed ratio `r = N/N_ref`, CleanroomX applies the classical fan affinity-law scaling to every supplied reference fan-curve point:

    Q_r = Q_ref * r
    ΔP_r = ΔP_ref * r²
    P_scale = r³

The first two relations create a transformed fan curve at the requested speed ratio. That transformed curve is then passed to the existing CleanroomX bounded fan/system operating-point solver.

The solver still:

- interpolates only between transformed supplied fan-curve points;
- evaluates the explicit system model `ΔP = ΔP_fixed + R·Q²`;
- reports `no_intersection_in_supplied_range` instead of extrapolating;
- calculates fluid air power as `Q × ΔP`.

The reported cubic power ratio is an affinity-law scaling indicator relative to the reference fan speed. It is not motor input power and does not apply a motor, drive, or fan-efficiency model.

## Input

Example:

```json
{
  "name": "VFD fan-speed operating-point sweep",
  "reference_speed_rpm": 1800.0,
  "speed_ratios": [0.5, 0.75, 1.0],
  "reference_fan_curve": {
    "name": "Reference fan",
    "points": [
      {"airflow_m3_h": 0.0, "pressure_pa": 600.0},
      {"airflow_m3_h": 3000.0, "pressure_pa": 500.0},
      {"airflow_m3_h": 6000.0, "pressure_pa": 300.0}
    ]
  },
  "system_curve": {
    "name": "System",
    "fixed_pressure_pa": 80.0,
    "resistance_pa_per_m3_s_squared": 100.0
  }
}
```

`reference_speed_rpm` is optional. When present, the report also shows the implied rpm for each speed ratio. CleanroomX does not invent a permitted VFD or fan-speed range.

## CLI

    cleanroomx-fan-speed examples/fan_speed_sweep_demo.json

JSON output:

    cleanroomx-fan-speed examples/fan_speed_sweep_demo.json --format json

Write a Markdown report:

    cleanroomx-fan-speed examples/fan_speed_sweep_demo.json --output fan-speed-report.md

The CLI exits with code 2 when one or more requested speed cases have no fan/system intersection inside the transformed supplied curve. This is a screening attention state, not an equipment rejection.

## Engineering boundary

Fan affinity laws are similarity relationships. Real fan performance can depart from ideal scaling because of Reynolds effects, efficiency changes, motor/VFD constraints, fan construction, stall/surge behavior, system effect, density changes, and manufacturer-specific operating limits.

CleanroomX therefore does not infer:

- allowable minimum or maximum fan speed;
- VFD frequency limits;
- motor current or electrical input power;
- efficiency curves or best-efficiency-point acceptance;
- stall/surge limits;
- acoustic performance;
- manufacturer selection or warranty applicability.

Use the actual manufacturer fan data, drive/motor limits, applicable design requirements, and qualified engineering review for equipment decisions.

## References

- U.S. Department of Energy, Better Buildings / Better Plants — Fans: https://betterbuildingssolutioncenter.energy.gov/better-plants/fans
- U.S. Department of Energy, *Improving Fan System Performance: A Sourcebook for Industry*: https://www.energy.gov/sites/prod/files/2014/05/f16/fan_sourcebook.pdf

The DOE resources describe variable-speed control as a fan-system energy-performance measure and document fan affinity-law use for speed-dependent performance.
