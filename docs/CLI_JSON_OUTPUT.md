# CLI strict JSON output boundary

CleanroomX engineering CLIs that emit JSON must produce standards-compliant JSON, not Python's permissive NaN/Infinity extensions.

This workstream hardens these stable file-backed commands:

- cleanroomx-hvac
- cleanroomx-recovery-test
- cleanroomx-duct-flow
- cleanroomx-dossier

Before JSON is serialized, the result is passed through the canonical strict-JSON clone. The boundary rejects non-finite floats, non-string object keys, cyclic references, invalid UTF-8 strings, and Python-only value/container types. The encoder also uses allow_nan=False.

Serialization happens before atomic output replacement. Therefore, if a result is not representable as strict JSON, the command returns an operational error and an existing --output file is left unchanged.

This changes no solver equation, project schema, engineering acceptance criterion, or Markdown output path.
