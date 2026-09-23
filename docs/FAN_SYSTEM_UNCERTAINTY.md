# Fan/system operating-point uncertainty

CleanroomX v0.24 adds deterministic bounded uncertainty screening around the existing fan/system operating-point solver.

## Model

The supplied fan curve is held fixed. The system curve remains:

```text
ΔP_system = ΔP_fixed + R × Q²
```

The input file can assign absolute uncertainty bounds to:

- fixed system pressure `ΔP_fixed`;
- quadratic resistance `R`.

CleanroomX evaluates every unique lower/upper corner of those two bounded inputs and solves each corner using the existing bounded fan-curve intersection solver.

## Conservative result handling

An operating-point airflow/pressure envelope is reported only when the nominal case and every bounded corner intersect the supplied fan curve.

If any corner would require fan-curve extrapolation, the analysis status is `indeterminate` and the complete envelope is withheld. Solved corners remain visible for diagnosis, but they are not presented as a complete uncertainty bound.

Air power remains available at the nominal and individual solved corner operating points, but CleanroomX does not label the corner min/max as a conservative air-power envelope because `Q × ΔP` can have an interior extremum along a piecewise-linear fan-curve segment.

This avoids converting a partially covered uncertainty box into a false min/max result.

## Input example

```json
{
  "name": "Supply fan uncertainty",
  "fan_curve": {
    "name": "Manufacturer curve",
    "provenance": {
      "source_type": "manufacturer_data",
      "source_name": "Fan schedule",
      "reference": "FAN-001"
    },
    "points": [
      {"airflow_m3_h": 0, "pressure_pa": 600},
      {"airflow_m3_h": 3000, "pressure_pa": 500},
      {"airflow_m3_h": 6000, "pressure_pa": 300}
    ]
  },
  "system_curve": {
    "name": "Bounded system",
    "fixed_pressure_pa": {
      "value": 80,
      "uncertainty_abs": 20
    },
    "resistance_pa_per_m3_s_squared": {
      "value": 100,
      "uncertainty_abs": 20
    }
  }
}
```

Run:

```text
cleanroomx-fan-uncertainty examples/fan_uncertainty_demo.json
cleanroomx-fan-uncertainty examples/fan_uncertainty_demo.json --format json
```

## Scope boundary

This is deterministic corner analysis, not a statistical uncertainty budget. It does not assign probability distributions, model covariance, vary the supplied fan curve, infer fan-law scaling, extrapolate manufacturer data, solve variable-resistance controls, correct system effect, assess stall/surge, or make equipment-selection/acceptance decisions.
