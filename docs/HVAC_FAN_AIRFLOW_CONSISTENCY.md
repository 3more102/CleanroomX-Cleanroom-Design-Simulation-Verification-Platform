# HVAC / Fan Operating-Airflow Consistency

CleanroomX v0.22 can cross-check the HVAC governing airflow against the operating airflow produced by fan studies already included in an engineering dossier.

## Purpose

This check detects contradictory design inputs or study outputs across modules. It does not calculate a new fan operating point and does not change any fan or duct physics.

Supported fan-study results:

- standalone fan/system operating-point studies,
- reference-flow fan/duct-network operating-point studies,
- fan-driven passive parallel-network studies,
- individual cases from bounded fan-speed affinity-law studies.

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

The dossier must also include an `hvac_project` and at least one supported fan operating-point or fan-speed study. Each fan-speed case is compared independently because each solved speed ratio has its own operating airflow.

## Decision logic

For each fan operating point, including each fan-speed case, CleanroomX compares:

`fan operating airflow - HVAC total governing airflow`

A solved study is `match` when the absolute difference is less than or equal to the configured tolerance; otherwise it is `mismatch`.

An unsolved fan study or fan-speed case is `not_comparable`, because there is no operating airflow to compare. The overall status is:

- `fail` when at least one solved study mismatches,
- `not_comparable` when no included study has a solved operating point,
- `pass_with_unresolved_studies` when solved studies match but one or more other studies are unresolved,
- `pass` when all included studies are solved and match.

## Engineering boundary

The absolute airflow tolerance is supplied by the project. CleanroomX does not invent a default engineering acceptance band beyond exact agreement when the configured tolerance is zero. This workflow does not establish airflow adequacy, fan selection, fan stability, commissioning acceptance, cleanroom classification, certification, or a standards-derived tolerance.
