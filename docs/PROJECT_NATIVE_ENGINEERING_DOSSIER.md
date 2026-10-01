# Project-native engineering dossier

Release 3 adds a deterministic engineering dossier generated directly from the
canonical saved CleanroomX project.

This closes the project-native traceability path:

```text
Project geometry / analysis definitions
→ project requirements
→ explicit requirement-to-result mappings
→ immutable analysis run history
→ persisted canonical verification history
→ project diagnostics
→ project engineering dossier
```

The existing `cleanroomx-dossier` remains available for legacy multi-file
engineering dossier manifests. The project-native dossier is a separate read-only
projection of the canonical desktop project.

## CLI

```text
cleanroomx-project-dossier project.cleanroomx.json
cleanroomx-project-dossier project.cleanroomx.json --format markdown
cleanroomx-project-dossier project.cleanroomx.json --output dossier.json
```

Successful JSON output uses schema
`cleanroomx.project-engineering-dossier`, version 1.

## Desktop workflow

Use **File → Export Project Engineering Dossier...** after saving the project.
The desktop exporter refuses unsaved changes because the dossier must be bound to
exact on-disk project bytes. It also refuses export if the saved project changed
externally after it was opened or last saved.

Choose a `.json` destination for the complete machine-readable evidence artifact
or a `.md` destination for the review-oriented Markdown projection.

## Exact project binding

The dossier records `source_project_revision`, the SHA-256 of the exact saved
project bytes used to create the dossier. The source is checked again after dossier
generation. If the project changes during generation, the report is discarded.

The dossier also has `dossier_sha256`, computed over the complete canonical
dossier body excluding that digest field.

## Included evidence

The dossier includes:

- project identity, active analysis, and current analysis definitions/inputs;
- normalized first-class project requirements and their SHA-256 identity;
- normalized explicit requirement-evidence mappings and their SHA-256 identity;
- complete retained analysis-run ledger records and ledger integrity summary;
- complete retained project-verification ledger records and integrity summary;
- compact latest-retained verification summary per analysis, with the current
  verification-currency assessment attached to that historical record;
- deterministic project diagnostics, including spatial/model/provenance findings;
- explicit engineering-boundary statements.

Because retained run and verification ledgers are bounded by their existing
persistence policies, the dossier contains the complete retained history, not an
unbounded lifetime archive.

## Historical evidence semantics

A persisted verification record remains bound to the
`project_source_revision` stored in that record. Adding the record itself creates
a newer saved-project file revision. Therefore the dossier intentionally does not
label a historical record as verification of later project edits merely because it
is the newest retained record.

The exact source hashes remain visible so a reviewer can determine what evidence
was generated from which revision.

The latest-retained verification table deliberately separates **Historical
status** from **Current currency**. A retained historical `pass` therefore remains
a truthful statement about the revision that was verified, while the adjacent
currency state reports whether the same verification still matches the current
analysis input, requirements, mappings, active mapping set, and—when provable—the
content of file-backed engineering dependencies. Proven configuration/content
changes are shown as `stale`; unresolved dependency freshness remains
`dependency_freshness_unverifiable` rather than being promoted to current.

## Output safety

When `--output` is used, the project source and registered external engineering
dependencies are protected from accidental overwrite. Publication uses the
existing atomic text-write boundary.

## Engineering boundary

SHA-256 hashes and chained ledgers detect accidental mutation and corruption but
are not digital signatures. A party able to rewrite the project can recompute
hashes.

A CleanroomX dossier is engineering evidence and traceability support. It does not
replace commissioning, testing/adjusting/balancing, CFD validation, independent
engineering review, regulatory approval, or cleanroom certification.
