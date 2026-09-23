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
- zero or more standalone psychrometric-state uncertainty analyses;
- zero or more fan/system operating-point studies;
- zero or more bounded fan/system uncertainty analyses;
- zero or more reference-flow fan/duct-network operating-point studies;
- zero or more fan-driven passive parallel-network operating-point studies;
- zero or more fan-driven fixed-resistance loop-network operating-point studies;
- zero or more bounded fan/loop-network uncertainty analyses;
- zero or more explicit loop damper-resistance scenario studies;
- zero or more fan affinity-law speed studies;
- zero or more fan-speed/fixed-resistance-loop studies;
- zero or more fan/variable-friction-loop operating-point studies;
- zero or more fan-speed/variable-friction-loop studies;
- zero or more bounded fan/variable-friction-loop uncertainty analyses;
- an optional v0.17 verification/HVAC duplicated-input consistency check;
- an optional v0.22 HVAC/fan operating-airflow consistency check with project-supplied absolute tolerance.

Paths are resolved relative to the manifest file. Existing manifests that omit optional analysis lists or consistency checks remain valid.

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
  "psychrometric_uncertainty_analyses": ["psychrometric_uncertainty_demo.json"],
  "fan_operating_point_studies": ["fan_operating_point_demo.json"],
  "fan_system_uncertainty_analyses": ["fan_uncertainty_demo.json"],
  "fan_duct_network_studies": ["fan_duct_network_demo.json"],
  "fan_parallel_network_studies": ["fan_parallel_network_demo.json"],
  "fan_loop_network_studies": ["fan_loop_network_demo.json"],
  "fan_loop_uncertainty_analyses": ["fan_loop_uncertainty_demo.json"],
  "damper_studies": ["damper_study_demo.json"],
  "fan_speed_studies": ["fan_speed_dossier_demo.json"],
  "fan_loop_speed_studies": ["fan_loop_speed_demo.json"],
  "fan_variable_friction_loop_studies": ["fan_variable_friction_loop_demo.json"],
  "fan_variable_friction_speed_studies": ["fan_variable_friction_speed_demo.json"],
  "fan_variable_friction_uncertainty_analyses": ["fan_variable_friction_uncertainty_demo.json"],
  "consistency_checks": {
    "verification_hvac_airflow": {
      "room_airflow_abs_tolerance_m3_h": 0.0,
      "require_same_room_set": true
    }
  }
}
```

## Cross-module consistency

The optional `verification_hvac_airflow` block reuses the v0.17 standalone consistency engine. It compares the verification project's `supply_airflow_m3_h` against the HVAC project's `cleanroom_airflow_m3_h` for exact matching room names.

Supported dossier options are the same as the standalone checker:

- `room_airflow_abs_tolerance_m3_h`: user-supplied absolute duplicated-input tolerance, default `0.0 m³/h`;
- `require_same_room_set`: when true, rooms present in only one project make the consistency result fail.

A `fail` contributes to dossier attention tracking. `not_comparable` is preserved as an unresolved item instead of being promoted to pass. `pass_with_scope_difference` remains visible in the dossier but is not converted into a failure when identical room sets were not required.

Both `verification_project` and `hvac_project` are required when this consistency block is configured. The already-hashed source files are reused; no duplicate input files are introduced.

The optional `hvac_fan_operating_airflow` check can compare HVAC governing airflow against solved standalone fan/system, reference-flow fan/duct, passive parallel-network, fixed-resistance fan/loop-network, fan/variable-friction-loop, standalone fan-speed, fixed-resistance fan-speed/loop, variable-friction fan-speed/loop, and every evaluated fan/variable-friction uncertainty corner. Each uncertainty corner remains an explicit comparison record; unresolved or numerically non-converged corners are preserved as `not_comparable` rather than fabricated into airflow values.

See `docs/CROSS_MODULE_CONSISTENCY.md` for the standalone checker and its engineering boundary.

## Traceability

Each referenced source file is hashed byte-for-byte with SHA-256. The report records the supplied relative path, analysis kind, and digest so a reviewer can verify exactly which input files produced the dossier.

## Executive state

The dossier preserves component-specific states instead of turning every result into a certification verdict:

- `attention_required`: one or more configured checks failed, a recovery test is incomplete or indeterminate, an uncertainty result is indeterminate, a bounded fan/system uncertainty analysis has an unresolved corner, a configured cross-module consistency check failed, any bounded fan case has no intersection inside the supplied fan-curve range, or a nonlinear fan/variable-friction solve is `non_converged`;
- `complete_with_unchecked`: no attention item is present, but one or more configured acceptance checks remain `not_checked`, a configured consistency check is `not_comparable`, an HVAC/fan airflow comparison has unresolved fan cases, or a standalone psychrometric/fan-system uncertainty analysis has incomplete provenance;
- `no_adverse_findings`: no attention or unchecked acceptance states are present.

A recovery result that is indeterminate because its supplied concentration-uncertainty interval overlaps the target is preserved as an attention item rather than being promoted to pass or collapsed into fail. Solved standalone, reference-flow fan/duct, passive parallel-network, fixed-resistance fan/loop-network, and fan-speed operating points are reported as bounded engineering screening, not equipment acceptance. Damper scenarios remain explicit resistance sensitivity studies and do not infer damper position or balancing acceptance. A complete fan/system uncertainty airflow/pressure envelope is reported only when every bounded system corner intersects the supplied fan curve; otherwise the analysis remains indeterminate. A completed psychrometric-state envelope is likewise screening rather than a conformity decision. Missing psychrometric, fan-system, or fan/loop uncertainty provenance is tracked as unresolved traceability rather than a numerical failure. Fan/loop uncertainty becomes an attention item when one or more configured corners are unresolved; fan-speed/loop studies become attention items when any transformed curve has no bounded intersection. The nonlinear v0.33/v0.34 fan/variable-friction workflows additionally make every `non_converged` result an attention item, preserve termination/residual evidence, and never promote numerical failure to PASS. The v0.37 nonlinear uncertainty workflow is dossier-integrated in v0.38 and retains the v0.41 physical/geometry bounds: an `indeterminate` uncertainty analysis is an attention item, while incomplete fan-curve/fixed-pressure/local-loss/roughness/viscosity/density/length/dimension provenance is tracked separately as unresolved traceability. Complete corner envelopes are preserved only when the nominal case and every configured corner solve. HVAC calculations remain preliminary screening.

## CLI

```text
cleanroomx-dossier examples/dossier_demo.json
cleanroomx-dossier examples/dossier_demo.json --format json
cleanroomx-dossier examples/dossier_demo.json --output dossier.md
```

The CLI exits with code 2 when the dossier state is `attention_required`; otherwise it exits with code 0. Detailed component states remain available in the JSON/Markdown output.

## Boundary

The dossier is an aggregation of CleanroomX calculations against user-configured project criteria and bounded engineering models. Final cleanroom classification, qualification, commissioning, regulatory approval, fan/equipment selection, and acceptance remain governed by the applicable licensed standards, client/project requirements, approved procedures, calibrated instrumentation, manufacturer data, and qualified engineering judgment.
