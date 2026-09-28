# CLI strict JSON output boundary

CleanroomX engineering CLIs that emit JSON must produce standards-compliant JSON, never Python's permissive NaN/Infinity extensions.

This boundary currently covers:

- `cleanroomx-hvac`
- `cleanroomx-recovery-test`
- `cleanroomx-duct-flow`
- `cleanroomx-dossier`

Before encoding, result values are copied into ordinary JSON containers. Immutable list/dict subclasses used by completed analysis snapshots remain compatible, and tuples that were historically JSON-encoded as arrays are normalized to plain arrays. Non-finite numbers, invalid UTF-8 text, non-string object keys, cycles, and unsupported Python-only values are rejected with `StrictJSONError`.

The final encoder also uses `allow_nan=False`. Serialization completes before atomic output replacement, so a serialization failure leaves an existing `--output` file unchanged.

This changes no solver equation, project schema, engineering acceptance criterion, or Markdown output path.
