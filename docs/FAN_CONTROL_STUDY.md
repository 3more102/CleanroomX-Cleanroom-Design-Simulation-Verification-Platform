# Fan-control state study

CleanroomX v0.19 adds a bounded study for explicit discrete fan-control states. It is intended for cases where the project has separate measured, manufacturer-supplied, or otherwise justified fan curves at specific control commands.

## Model

Each state supplies:

- a state name;
- a control signal from 0 to 100 percent;
- its own explicit fan pressure/airflow curve.

All states share one explicit CleanroomX system curve:

    delta_p_system = delta_p_fixed + R * Q^2

For every state, CleanroomX reuses the existing bounded fan/system operating-point solver. Fan pressure is interpolated only between points on that state's supplied curve. No fan-curve extrapolation is performed.

Control signals must be strictly increasing. CleanroomX then checks whether the solved airflow is non-decreasing across the solved states. A decreasing response is reported as an attention condition because the explicit supplied curves do not show a monotonic airflow response to increasing command.

## Optional target airflow

A study may provide:

- `target_airflow_m3_h`;
- `target_tolerance_m3_h`.

Each solved state is classified as:

- `below_target_band`;
- `within_target_band`;
- `above_target_band`.

A state with no bounded fan/system intersection is `not_comparable` for the target check. CleanroomX also reports the solved state numerically closest to the target.

The target and tolerance are project inputs. CleanroomX does not invent a cleanroom acceptance tolerance.

## JSON input

    {
      "name": "Supply fan discrete control-state demo",
      "system_curve": {
        "name": "Example cleanroom duct system",
        "fixed_pressure_pa": 0.0,
        "resistance_pa_per_m3_s_squared": 100.0
      },
      "target_airflow_m3_h": 5400.0,
      "target_tolerance_m3_h": 100.0,
      "states": [
        {
          "name": "Low command",
          "control_signal_percent": 40.0,
          "fan_curve": {
            "name": "Explicit 40% fan curve",
            "points": [
              {"airflow_m3_h": 0.0, "pressure_pa": 300.0},
              {"airflow_m3_h": 3600.0, "pressure_pa": 100.0}
            ]
          }
        },
        {
          "name": "Mid command",
          "control_signal_percent": 60.0,
          "fan_curve": {
            "name": "Explicit 60% fan curve",
            "points": [
              {"airflow_m3_h": 0.0, "pressure_pa": 425.0},
              {"airflow_m3_h": 5400.0, "pressure_pa": 225.0}
            ]
          }
        }
      ]
    }

Run:

    cleanroomx-fan-control examples/fan_control_demo.json

JSON output:

    cleanroomx-fan-control examples/fan_control_demo.json --format json

## Engineering boundary

This is a discrete steady-state screening study. CleanroomX does not scale one curve into another with fan affinity laws, interpolate fan curves between control commands, infer a VFD transfer function, simulate closed-loop controller dynamics, calculate motor/electrical input power, assess stall/surge boundaries, or perform manufacturer equipment selection.

The explicit curves should come from an appropriate project source such as manufacturer data, test data, or another documented engineering basis.

## References

The fan/system operating-point method reused here is documented in `docs/FAN_SYSTEM_OPERATING_POINT.md`.

ASHRAE fan guidance discusses matching fan performance with system resistance at the operating point:

https://handbook.ashrae.org/Handbooks/S24/SI/S24_Ch21/S24_Ch21_si.aspx

The U.S. Department of Energy fan sourcebook describes fan performance curves and system curves for fan-system analysis:

https://www.energy.gov/sites/default/files/2014/05/f16/fan_sourcebook.pdf
