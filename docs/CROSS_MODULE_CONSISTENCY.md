# Cross-module consistency checks

CleanroomX can reconcile independent inputs and results across analysis modules. The first check compares room supply airflow between multi-room verification and preliminary HVAC analysis.

## Verification to HVAC airflow

For each configured room pair, verification airflow is reconstructed from the reported room volume and ACH:

~~~text
verification airflow = room volume × ACH
~~~

It is compared with the HVAC room's independently entered `cleanroom_airflow_m3_h`.

The absolute percentage deviation is:

~~~text
|HVAC airflow - verification airflow| / verification airflow × 100
~~~

A room pair passes only when that deviation is less than or equal to the explicitly supplied `airflow_tolerance_percent`.

## Dossier configuration

~~~json
{
  "consistency_checks": {
    "verification_hvac_airflow": {
      "airflow_tolerance_percent": 1.0,
      "room_map": {
        "Process": "Process Bay"
      },
      "require_all_verification_rooms": false,
      "require_all_hvac_rooms": false
    }
  }
}
~~~

- `airflow_tolerance_percent` is mandatory when the check is configured. CleanroomX does not invent a default engineering tolerance.
- If `room_map` is omitted, rooms are paired by exact matching names.
- `room_map` is one-to-one; duplicate HVAC targets are rejected.
- Unknown room names in an explicit map are rejected as configuration errors.
- `require_all_verification_rooms` makes any unmapped verification room a failed consistency requirement.
- `require_all_hvac_rooms` does the same for HVAC rooms.
- If the check is configured but no room pairs can be formed, the result is `not_checked` rather than a pass.

## Dossier state

Failed comparisons and required unmapped rooms contribute to the dossier's `attention_required` state. A configured-but-uncheckable consistency check contributes one unresolved item and therefore produces `complete_with_unchecked` when no adverse items exist.

## Boundary

This workflow detects contradictions between CleanroomX inputs and results. It does not establish airflow adequacy, cleanroom classification, commissioning acceptance, or a universal tolerance. The tolerance must come from the project's approved engineering or QA basis.
