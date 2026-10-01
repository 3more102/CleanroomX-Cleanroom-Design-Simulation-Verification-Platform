# Project Requirements Traceability

`cleanroomx-project-traceability` is a read-only Release 3 operator and automation
surface for the first-class project requirements registry and persisted
requirement-to-analysis evidence mappings.

It does **not** run engineering analysis, infer standards criteria, convert units,
or issue a verification verdict. It projects only canonical persisted project data.

## Usage

```bash
cleanroomx-project-traceability project.cleanroomx.json
cleanroomx-project-traceability project.cleanroomx.json --format markdown
cleanroomx-project-traceability project.cleanroomx.json --output traceability.json
```

JSON output is strict finite JSON and contains:

- the exact saved project SHA-256 and byte size;
- requirements and mappings registry SHA-256 identities;
- deterministic requirement-set, requirement, mapping, and active-mapping counts;
- lifecycle, applicability, scope, source, and explicit criterion fields;
- requirement-to-analysis mapping identity, subject, engineering property, and exact result path;
- current reference state for each retained mapping.

Active mappings are validated with the same canonical cross-project validation used
by project persistence. An active mapping that references an unknown requirement,
unknown analysis, mismatched analysis kind, or invalid subject fails closed.

Disabled or superseded mappings are historical traceability. A retained analysis
identifier is considered resolved only when the current analysis also matches the
mapping's recorded analysis kind. Reusing an ID for a different analysis kind does
not silently rebind historical evidence.

## Stable-source boundary

The CLI loads one exact saved project revision and rechecks the source bytes after
building the report. If the project changes during inspection, the report is
discarded. An `--output` path may not replace the project itself or any declared
file-backed engineering dependency.
