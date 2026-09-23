# Fan-speed control scenario study

CleanroomX v0.19 adds a bounded speed-scenario workflow for one supplied reference fan curve and one explicit system curve.

## Simplified fan affinity scaling

For the same fan geometry and comparable air conditions, each user-supplied speed ratio `r = N2/N1` scales the reference fan curve as:

    Q2 = Q1 * r
    delta_p2 = delta_p1 * r^2

These are the simplified fan affinity-law relations used by the U.S. Department of Energy fan sourcebook and by AMCA fan-engineering guidance.

CleanroomX applies the relations point-by-point to the supplied reference curve. It then reuses the existing bounded fan/system solver against the unchanged explicit system model:

    delta_p_system = delta_p_fixed + R * Q^2

No fan pressure is extrapolated beyond the airflow range of the speed-scaled curve.

## Inputs

A study supplies:

- a study name;
- a reference fan curve;
- an explicit fixed-plus-quadratic system curve;
- one or more positive, unique speed ratios;
- optionally, the RPM associated with the reference fan curve;
- optionally, a project-required airflow for screening the discrete tested scenarios.

The speed ratios are not inferred by CleanroomX and are not treated as manufacturer-approved operating limits.

## Outputs

For each tested speed ratio, CleanroomX reports:

- the scaled fan-curve points;
- speed percentage and optional RPM;
- bounded fan/system operating-point status;
- operating airflow, pressure, and air power when an intersection exists;
- optional comparison with the configured required airflow.

If a required airflow is provided, CleanroomX reports the **lowest tested speed scenario** that meets it. It does not interpolate between tested speed ratios or claim that the reported ratio is a continuous optimum.

## JSON example

    {
      "name": "Supply fan speed-control scenario demo",
      "reference_speed_rpm": 1450.0,
      "required_airflow_m3_h": 5000.0,
      "speed_ratios": [0.6, 0.8, 1.0, 1.1],
      "reference_fan_curve": {
        "name": "Example manufacturer reference fan curve",
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

    cleanroomx-fan-control examples/fan_speed_control_demo.json

JSON output:

    cleanroomx-fan-control examples/fan_speed_control_demo.json --format json

## Engineering boundary

This is a deterministic engineering-screening workflow, not a VFD controller, fan selection program, or commissioning acceptance method. It does not infer allowable RPM, motor loading, VFD limits, fan efficiency, density corrections, compressibility, stall/surge boundaries, structural speed limits, control-loop stability, acoustics, system effect, or manufacturer approval.

The simplified fan laws assume the same fan geometry and comparable air conditions. Manufacturer performance data and limits govern real equipment operation. AMCA notes that more advanced affinity-law treatment can require density and compressibility considerations; its current training guidance specifically highlights compressibility for high-pressure systems.

## References

- U.S. Department of Energy, *Improving Fan System Performance: A Sourcebook for Industry*: https://www.energy.gov/sites/prod/files/2014/05/f16/fan_sourcebook.pdf
- AMCA International, *Fan Science and Engineering: Fan Affinity Laws — Simplified*: https://learning.amca.org/store/4938636-fan-science-and-engineering-fan-affinity-laws-simplified
- AMCA International, *Fan Science and Engineering: Advanced Affinity Laws*: https://learning.amca.org/store/4938294-fan-science-and-engineering-advanced-affinity-laws
