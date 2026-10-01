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

The list output is strict JSON and contains:

- project source SHA-256 and byte size;
- verification ledger record count, sequence range, anchor, and head hash;
- compact per-record verification status;
- fail-closed verification-currency assessment against the current project configuration;
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
the chained record hash.

## Stable-read boundary

The command loads the project through the canonical project parser, so the
verification ledger is integrity-validated before output. It captures the project
file revision before and after inspection and emits nothing if the file changes
during the operation.

The command is read-only. It does not rewrite the project, recompute historical
verdicts, or silently bind old evidence to current project state.

## Verification currency

The operator output also assesses each current analysis against its latest retained
verification record.

A record is reported as `current` only when its analysis kind, canonical input
SHA-256, requirements SHA-256, mappings SHA-256, and active mapping identities all
still match and the analysis declares no file-backed external engineering inputs.

If configuration changed, the state is `stale`. If active mappings exist but no
record is retained, the state is `not_verified`. Analyses without active mappings
are `not_configured`.

Schema-v1 verification records do not retain the file fingerprints needed to prove
that external dependency bytes are unchanged. Therefore a matching file-backed
analysis is reported as `dependency_freshness_unverifiable`, never as current.

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
