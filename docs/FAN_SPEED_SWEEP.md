# Fan affinity-law speed sweep

CleanroomX v0.19 adds a bounded steady-state speed sweep for one reference fan curve and one explicit system curve.

## Model

For each user-supplied speed ratio r = N2/N1, CleanroomX scales the reference fan-curve coordinates using the incompressible constant-density fan-law relationships:

    Q2 = Q1 * r
    deltaP2 = deltaP1 * r^2
    power_ratio = r^3

The scaled fan curve is then passed to the existing bounded fan/system operating-point solver. The system model remains:

    deltaP_system = deltaP_fixed + R * Q^2

No fan-curve extrapolation is performed by the operating-point solver.

The cubic power ratio is reported only as the ideal fan-law ratio relative to the reference condition. It is not reported as shaft power, motor input power, VFD input power, or energy consumption.

## JSON input

    {
      "name": "Supply fan affinity-law speed sweep demo",
      "reference_speed_rpm": 1500.0,
      "speed_ratios": [1.0, 0.8, 0.6, 0.4],
      "reference_fan_curve": {
        "name": "Example manufacturer reference-speed fan curve",
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

    cleanroomx-fan-speed examples/fan_speed_sweep_demo.json

JSON output:

    cleanroomx-fan-speed examples/fan_speed_sweep_demo.json --format json

Write a Markdown report:

    cleanroomx-fan-speed examples/fan_speed_sweep_demo.json --output fan-speed-report.md

## Engineering boundary

This is a static affinity-law screening workflow, not a dynamic VFD or closed-loop control simulation. It assumes the same fan diameter and nominal gas density and uses ideal similarity-law scaling. It does not model efficiency variation, motor/VFD losses, control-loop dynamics, PID stability, damper action, system effect, variable friction, stall/surge limits, acoustics, manufacturer speed limits, or equipment acceptance.

Measured or manufacturer-rated performance at multiple speeds should be preferred when available.

## References

- ANSI/AMCA Standard 99-25, Standards Handbook, fan laws.
- AMCA Publication 211-22 (Rev. 01-23), fan-law speed conversion and multi-speed interpolation guidance.
- ANSI/AMCA Standard 210-25 / ANSI/ASHRAE 51-25, laboratory methods of testing fans for certified aerodynamic performance.
