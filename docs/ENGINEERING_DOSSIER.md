# Engineering dossier workflow

The CleanroomX engineering dossier combines existing analysis outputs into one auditable Markdown or JSON package. It is a reporting and traceability layer; it does not create new acceptance limits and it does not convert CleanroomX screening into certification.

## Manifest

A dossier manifest can reference:

- one multi-room verification project;
- one HVAC/duct project;
- zero or more measured recovery tests;
- zero or more uncertainty-aware qualification analyses;
- zero or more uncertainty/provenance room inputs.

Paths are resolved relative to the manifest file.

Example:

```json
{
  "name": "Qualification Package",
  "project_reference": "CR-001",
  "revision": "A",
  "verification_project": "facility_project.json",
  "hvac_project": "duct_network_demo.json",
  "recovery_tests": ["recovery_test_demo.json"],
  "qualification_analyses": ["qualification_uncertainty_demo.json"],
  "uncertainty_rooms": ["uncertainty_room_demo.json"]
}
```

## Traceability

Each referenced source file is hashed byte-for-byte with SHA-256. The report records the supplied relative path, analysis kind, and digest so a reviewer can verify exactly which input files produced the dossier.

## Executive state

The dossier preserves component-specific states instead of turning every result into a binary pass/fail:

- `attention_required`: one or more configured checks failed, a recovery test is incomplete, or an uncertainty/qualification result is indeterminate;
- `complete_with_unchecked`: no adverse findings are present, but one or more configured analysis records remain `not_checked`;
- `no_adverse_findings`: no adverse or unchecked acceptance states are present.

HVAC is labeled as engineering screening. Air-balance shortfalls are surfaced as attention items, but the dossier state is not a certification result.

## CLI

```text
cleanroomx-dossier examples/dossier_demo.json
cleanroomx-dossier examples/dossier_demo.json --format json
cleanroomx-dossier examples/dossier_demo.json --output dossier.md
```

The CLI exits with code 2 when the dossier state is `attention_required`; otherwise it exits with code 0. Detailed component states remain available in the JSON/Markdown output.

## Boundary

The dossier is an aggregation of CleanroomX calculations against user-configured project criteria. Final cleanroom classification, qualification, commissioning, regulatory approval, and acceptance remain governed by the applicable licensed standards, client/project requirements, approved procedures, calibrated instrumentation, and qualified engineering judgment.
