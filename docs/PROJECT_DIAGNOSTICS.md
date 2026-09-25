# Project Diagnostics

CleanroomX project diagnostics provide one deterministic, read-only project health scan across existing model, spatial, synchronization, analysis-input, and execution-provenance rules.

Run:

```bash
cleanroomx-project-check project.cleanroomx.json
```

Markdown output:

```bash
cleanroomx-project-check project.cleanroomx.json --format markdown
```

Atomic file output:

```bash
cleanroomx-project-check project.cleanroomx.json --output project-diagnostics.json
```

## What is checked

The checker composes existing CleanroomX authorities rather than introducing parallel engineering logic.

- **Spatial integrity** reuses the spatial workspace validator for overlapping rooms, duplicate room names, unassigned/orphan devices, devices outside assigned rooms, invalid elevations, and wall-opening placement.
- **Analysis input validity** runs every saved analysis through its real application parser/validation path. File-backed workflows are resolved relative to the checked project.
- **Engineering synchronization** evaluates the explicitly persisted spatial synchronization authority and reports geometry-newer, engineering-newer, conflicting, unmapped, missing-analysis, and unsupported-contract states.
- **Run-history freshness** reuses application provenance hashes and external-dependency fingerprints. Retained evidence is current only when the analysis kind/input match and every recorded file-backed dependency still matches by content.
- **Traceability hygiene** distinguishes analyses that have never been run from analyses whose retained evidence no longer matches current inputs, and identifies run-history evidence for removed analyses.
- **Analysis naming** reports duplicate display names as an ambiguity warning while stable analysis IDs remain authoritative.

The checker does not mutate the project, execute engineering solvers, or add project-schema fields.

## Severity and exit codes

Diagnostics use three severities:

- `error` — inconsistent or invalid project state that should be corrected before relying on the affected workflow.
- `warning` — actionable model/provenance state requiring engineering review.
- `info` — incomplete but not intrinsically invalid state, such as an analysis with no retained run evidence.

The JSON summary status is `error`, `warning`, or `pass`. Informational findings do not downgrade `pass`.

The CLI returns:

- `0` when there are no errors or warnings;
- `1` when one or more errors or warnings are reported;
- `2` when the project cannot be checked safely (for example invalid project JSON, I/O failure, or a source-file revision change during the check).

## Source revision and data safety

The CLI loads one stable project revision, runs diagnostics against that in-memory project, then fingerprints the source again. If the source content changed during the check, the report is discarded.

JSON/Markdown `--output` files use the same durable atomic-write boundary as other CleanroomX exports, so a failed staging write or replacement does not intentionally truncate a previously valid report.

The diagnostics service itself is read-only and therefore does not participate in Undo/Redo.

## Engineering boundary

This feature is a project/model health checker. It does not invent ISO, GMP, regulatory, commissioning, TAB, manufacturer, or project acceptance criteria.

A `pass` means the configured CleanroomX software/model/provenance checks found no errors or warnings. It does **not** establish cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance. Applicable standards and acceptance criteria remain explicit project inputs.
