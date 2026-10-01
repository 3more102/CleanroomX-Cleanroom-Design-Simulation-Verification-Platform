# CLI strict JSON output boundary

CleanroomX engineering CLIs that emit JSON must produce standards-compliant JSON, never Python's permissive NaN/Infinity extensions.

This boundary covers every standalone file-backed engineering CLI that exposes JSON result output, including HVAC, recovery, duct/network/fan solvers, uncertainty and qualification studies, consistency checks, and dossiers. New result-producing CLI paths are regression-gated against direct permissive `json.dumps(result, ...)` serialization.

Before encoding, result values are copied into ordinary JSON containers. Immutable list/dict subclasses used by completed analysis snapshots remain compatible, and tuples that were historically JSON-encoded as arrays are normalized to plain arrays. Non-finite numbers, invalid UTF-8 text, non-string object keys, cycles, and unsupported Python-only values are rejected with `StrictJSONError`.

The final encoder also uses `allow_nan=False`. Each CLI converts its result through this boundary before publication; serialization failure is reported explicitly and occurs before atomic output replacement, so an existing `--output` file remains unchanged.

This changes no solver equation, project schema, engineering acceptance criterion, or Markdown output path.


## Protected file output

Standalone file-backed engineering CLIs publish `--output` through one protected
atomic writer. A report destination is rejected when it resolves to, or is an
existing same-file alias of, an engineering input. The identity check is repeated
immediately before atomic replacement so an output path cannot be changed into an
input alias during analysis and then published over that input.

For single-file studies the protected set contains the study/network/project input.
`cleanroomx-consistency` protects both source projects. `cleanroomx-dossier`
protects its manifest plus every declared file-backed dependency resolved relative
to the manifest directory. This guard is data-loss protection only; it does not
change solver equations, numerical tolerances, report contents, or exit semantics.
