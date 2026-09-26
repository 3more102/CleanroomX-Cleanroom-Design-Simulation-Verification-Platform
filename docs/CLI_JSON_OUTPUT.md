# CLI strict JSON output boundary

CleanroomX engineering CLIs that emit JSON must produce standards-compliant JSON, not Python's permissive NaN/Infinity extensions.

This workstream hardens these stable file-backed commands:

- cleanroomx-hvac
- cleanroomx-recovery-test
- cleanroomx-duct-flow
- cleanroomx-dossier

Before JSON is serialized, the result is checked for non-finite numbers, invalid UTF-8 strings, and cyclic containers. Existing JSON-compatible immutable container subclasses used by completed analysis snapshots remain supported. The encoder uses allow_nan=False as the final standards-compliance guard and normalizes unsupported serialization failures to the shared StrictJSONError boundary.

Serialization happens before atomic output replacement. Therefore, if a result is not representable as strict JSON, the command returns an operational error and an existing --output file is left unchanged.

This changes no solver equation, project schema, engineering acceptance criterion, or Markdown output path.
