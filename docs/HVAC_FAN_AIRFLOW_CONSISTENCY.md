# HVAC / Fan Operating-Airflow Consistency

CleanroomX v0.22 can cross-check the HVAC governing airflow against the operating airflow produced by fan studies already included in an engineering dossier.

## Purpose

This check detects contradictory design inputs or study outputs across modules. It does not calculate a new fan operating point and does not change any fan or duct physics.

Supported fan-study results:

- standalone fan/system operating-point studies;
- reference-flow fan/duct-network operating-point studies;
- fan-driven passive parallel-network studies;
- fixed-resistance fan/loop-network operating points;
- fan/variable-friction loop operating points;
- individual cases from standalone, fixed-resistance-loop, and variable-friction-loop fan-speed studies; and
- individual evaluated corners from nonlinear fan/variable-friction uncertainty analyses.

## Dossier configuration

```json
{
  "consistency_checks": {
    "hvac_fan_operating_airflow": {
      "airflow_abs_tolerance_m3_h": 1500.0
    }
  }
}
```

The dossier must also include an `hvac_project` and at least one supported fan workflow. Each fan-speed case is compared independently because each solved speed ratio has its own operating airflow. Each nonlinear uncertainty corner is also compared independently; an unresolved or non-converged corner remains `not_comparable` rather than being replaced by an envelope midpoint or fabricated airflow.

## Decision logic

For each fan operating point, fan-speed case, or evaluated nonlinear-uncertainty corner, CleanroomX compares:

`fan operating airflow - HVAC total governing airflow`

A solved study is `match` when the absolute difference is less than or equal to the configured tolerance; otherwise it is `mismatch`.

An unsolved fan study or fan-speed case is `not_comparable`, because there is no operating airflow to compare. The overall status is:

- `fail` when at least one solved study mismatches,
- `not_comparable` when no included study has a solved operating point,
- `pass_with_unresolved_studies` when solved studies match but one or more other studies are unresolved,
- `pass` when all included studies are solved and match.

## Engineering boundary

The absolute airflow tolerance is supplied by the project. CleanroomX does not invent a default engineering acceptance band beyond exact agreement when the configured tolerance is zero. This workflow does not establish airflow adequacy, fan selection, fan stability, commissioning acceptance, cleanroom classification, certification, or a standards-derived tolerance.
