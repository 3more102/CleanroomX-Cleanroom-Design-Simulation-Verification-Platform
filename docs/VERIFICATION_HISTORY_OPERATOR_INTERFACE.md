# Verification history operator interface

Release 3 persists canonical project-requirements verification as immutable historical
engineering evidence. The operator interface makes that ledger inspectable without
opening or editing the raw project JSON.

## CLI

Installed command:

`cleanroomx-verification-history`

### List retained verification evidence

```text
cleanroomx-verification-history list project.cleanroomx.json
```

Optional stable-analysis filter:

```text
cleanroomx-verification-history list project.cleanroomx.json --analysis-id room-a
```

The list output is strict JSON using inspection schema version 2 and contains:

- project source SHA-256 and byte size;
- verification ledger record count, sequence range, anchor, and head hash;
- compact per-record immutable verification status;
- a per-record `current_assessment` that labels the latest applicable record with
  canonical current/stale/unverifiable state, older records as `historical`, and
  records for removed analyses as `not_in_current_project`;
- the complete fail-closed project verification-currency assessment against the
  current project configuration and retained dependency fingerprints;
- canonical requirements, mappings, verification, workflow, engineering-identity,
  and record SHA-256 values.

Filtering changes only the returned record selection. The ledger summary always
describes the complete retained history.

### Show one complete persisted record

```text
cleanroomx-verification-history show project.cleanroomx.json --sequence 12
```

This returns the complete canonical persisted record, including exact evidence
locators, canonical findings, ProofGraph identities, runtime/code provenance, and
the chained record hash. The response also includes `record_currency`, derived from the canonical
verification-currency record-context helper. The historical record itself is not
modified.

## Stable-read boundary

The command loads the project through the canonical project parser, so the
verification ledger is integrity-validated before output. It captures the project
file revision before and after inspection and emits nothing if the file changes
during the operation.

The command is read-only. It does not rewrite the project, recompute historical
verdicts, or silently bind old evidence to current project state.

## Verification currency

The operator output also assesses each current analysis against its latest retained
verification record. Per-record CLI and desktop context is derived from the same
canonical verification-currency record-context helper so current, historical, and
removed-analysis states cannot drift between operator surfaces.

A record is reported as `current` only when its analysis kind, canonical input
SHA-256, requirements SHA-256, mappings SHA-256, and active mapping identities all
still match. For file-backed analyses, the retained dependency SHA-256 and byte
size must also match the current dependency content.

If configuration changed, the state is `stale`. If active mappings exist but no
record is retained, the state is `not_verified`. Analyses without active mappings
are `not_configured`.

New verification records retain the stable external engineering dependency
fingerprints captured by execution provenance. Resolvable dependency files are
re-fingerprinted and the verification is reported as `current` only if the
retained SHA-256 and byte size still match. A proven content mismatch is
`stale`.

Missing, unreadable, unstable, malformed, or unresolved dependency evidence is
reported as `dependency_freshness_unverifiable`; lack of readable evidence is
not treated as proof that content changed. Relative paths require the saved
project base directory, while absolute paths can be checked directly.

Legacy verification records created before dependency-fingerprint persistence
remain valid. If such a record is otherwise configuration-identical, it is also
reported as `dependency_freshness_unverifiable` rather than assumed current.

## Project diagnostics integration

`cleanroomx-project-check` now exposes:

- `project.verification_run_count`;
- top-level `verification_history` integrity/sequence summary;
- `verification_history.latest_by_analysis` compact latest-record summaries;
- top-level `verification_currency` with current/stale/unverifiable coverage.

The diagnostics report treats persisted verification evidence as historical
traceability. It does not reinterpret an old verdict as current-project
certification. Stale or dependency-unverifiable configured verification is emitted
as an actionable warning; mapped analyses with no persisted verification are
informational.

## Engineering boundary

The ledger and inspection interface provide tamper-evident engineering
traceability. SHA-256 chaining is not a digital signature. A user with permission
to rewrite the project file can recompute hashes. CleanroomX verification evidence
does not replace commissioning, TAB, CFD validation, independent review,
regulatory approval, or cleanroom certification.


## Desktop history review

Use **Analysis → Verification History...** to review the validated retained
project-verification ledger. The desktop history view shows sequence, completion
time, analysis identity, immutable historical verification status, current
verification currency, verified state, and engineering identity digest.

The **Requirement Evidence** tab expands every retained canonical finding into a
read-only requirement → evidence → verdict view. It shows subject scope, explicit
criterion, retained actual value/unit, evidence freshness, evidence source, and
the exact result locator captured by the immutable analysis binding. A finding
with no bound evidence remains explicit instead of being presented as a
successful check. The **Canonical Record** tab preserves the complete validated
record JSON for audit review.

Current verification currency is attached only to the latest retained record for
each analysis. Older retained records are labeled `historical` rather than being
presented as current. Records for analyses that are no longer present in the
current project are labeled `not_in_current_project`.

For the latest record, the desktop reuses the canonical verification-currency
assessment, including file-backed dependency checks against the saved-project
base directory. Proven configuration or dependency-content changes are shown as
`stale`; unresolved dependency freshness remains
`dependency_freshness_unverifiable`.

The dialog validates the ledger before display and refuses to present modified or
invalid history as trusted evidence. It does not rewrite any historical record or
historical verdict.
