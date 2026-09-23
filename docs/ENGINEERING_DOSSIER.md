# Engineering dossier workflow

The CleanroomX engineering dossier combines existing analysis outputs into one auditable Markdown or JSON package. It is a reporting and traceability layer; it does not create new acceptance limits and it does not convert CleanroomX screening into certification.

## Manifest

A dossier manifest can reference:

- one multi-room verification project;
- one HVAC/duct project, including its optional v0.12 fan-curve design-duty check;
- zero or more measured recovery tests;
- zero or more uncertainty-aware qualification analyses;
- zero or more uncertainty/provenance room inputs;
- zero or more thermal/HVAC uncertainty analyses;
- zero or more fan/system operating-point studies;
- an optional verification/HVAC airflow consistency check with an explicit project-supplied tolerance.

Paths are resolved relative to the manifest file. Existing manifests that omit the consistency block remain valid.

Example:

```json
{
  "name": "Qualification Package",
  "project_reference": "CR-001",
  "revision": "B",
  "verification_project": "facility_project.json",
  "hvac_project": "duct_network_demo.json",
  "recovery_tests": ["recovery_test_demo.json"],
  "qualification_analyses": ["qualification_uncertainty_demo.json"],
  "uncertainty_rooms": ["uncertainty_room_demo.json"],
  "thermal_uncertainty_analyses": ["thermal_uncertainty_demo.json"],
  "fan_operating_point_studies": ["fan_operating_point_demo.json"],
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
```

## Cross-module consistency

The optional `verification_hvac_airflow` check reconciles the supply airflow implied by each verification result (`volume × ACH`) with the HVAC module's independently entered `cleanroom_airflow_m3_h`.

No tolerance is embedded. When the check is configured, `airflow_tolerance_percent` is mandatory and must come from the project design or QA basis. Room pairs use exact-name matching by default. `room_map` can explicitly pair differently named rooms, and the two `require_all_...` flags can make unmapped rooms attention items.

A configured check reports `pass`, `fail`, or `not_checked`. It checks internal data consistency only; it does not determine whether the airflow itself is adequate.

See `docs/CROSS_MODULE_CONSISTENCY.md`.

## Traceability

Each referenced source file is hashed byte-for-byte with SHA-256. The report records the supplied relative path, analysis kind, and digest so a reviewer can verify exactly which input files produced the dossier.

## Executive state

The dossier preserves component-specific states instead of turning every result into a certification verdict:

- `attention_required`: one or more configured checks failed, a recovery test is incomplete, an uncertainty result is indeterminate, or a fan/system study has no intersection inside the supplied fan-curve range;
- `complete_with_unchecked`: no attention item is present, but one or more configured acceptance checks remain `not_checked`;
- `no_adverse_findings`: no attention or unchecked acceptance states are present.

A solved fan operating point is reported as completed engineering screening, not as equipment acceptance. HVAC calculations remain preliminary screening.

## CLI

```text
cleanroomx-dossier examples/dossier_demo.json
cleanroomx-dossier examples/dossier_demo.json --format json
cleanroomx-dossier examples/dossier_demo.json --output dossier.md
```

The CLI exits with code 2 when the dossier state is `attention_required`; otherwise it exits with code 0. Detailed component states remain available in the JSON/Markdown output.

## Boundary

The dossier is an aggregation of CleanroomX calculations against user-configured project criteria and bounded engineering models. Final cleanroom classification, qualification, commissioning, regulatory approval, fan/equipment selection, and acceptance remain governed by the applicable licensed standards, client/project requirements, approved procedures, calibrated instrumentation, manufacturer data, and qualified engineering judgment.
