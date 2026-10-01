# Persisted project verification runs

Release 3 persists canonical project-requirement verification as historical
engineering evidence inside the saved project.

The verification history is intentionally separate from analysis run history.
Analysis run history records solver execution. Project verification history
records the requirements/evidence/verdict boundary produced from immutable
analysis evidence.

## Metadata location

`project.metadata["cleanroomx.project_verification_run_history"]`

Schema:

- `cleanroomx.project-verification-run-history`
- schema version `1`
- canonicalization `json-sort-keys-compact-utf8-v1`

## Persisted evidence

Every verification record preserves:

- exact source-project SHA-256 used for the engineering execution;
- analysis ID, name and kind;
- integrity-verified analysis bundle SHA-256;
- exact analysis input SHA-256;
- normalized project requirements SHA-256;
- normalized requirement-evidence mappings SHA-256;
- stable active mapping IDs;
- full canonical requirement evidence records;
- exact `/result/...` evidence locators;
- evidence SHA-256;
- full canonical verification output, findings and completeness state;
- canonical verification SHA-256;
- ProofGraph SHA-256 identity for each projected graph;
- project-native workflow SHA-256;
- verifier module, qualified function name and verifier-source SHA-256;
- CleanroomX version;
- captured runtime environment;
- captured CleanroomX code revision provenance.

The ledger does not infer compliance or reimplement requirement comparison.

## Deterministic engineering identity

Each record has `verification_identity_sha256`.

That engineering identity is derived only from technical evidence and
implementation/runtime identities. It intentionally excludes:

- completion timestamp;
- history sequence;
- previous-record hash;
- storage record hash;
- filesystem path.

Running the same verified engineering evidence at a different wall-clock time
therefore retains the same engineering identity.

## Ledger integrity

Each persisted history record also has `record_sha256` and
`previous_record_sha256`.

Those values form a bounded chained ledger. They detect accidental mutation,
corruption and history discontinuity, but they are not digital signatures.
Anyone with permission to rewrite the project file can recompute hashes.

Retention is bounded by record count and serialized bytes. When older records
are pruned, the last removed record hash is retained as the history anchor so
the surviving chain remains internally verifiable.

## Guarded persistence

`persist_project_requirements_workflow_run(project_path, workflow)` persists a
completed project-native workflow only when the saved project is still
byte-for-byte the exact source revision that produced the workflow.

Before saving, the persistence boundary:

1. verifies the workflow component identities;
2. reloads the exact saved project revision;
3. confirms project/analysis identity;
4. confirms requirements and persisted mapping digests;
5. reconstructs canonical RequirementEvidence values;
6. reruns the canonical requirements verifier;
7. reruns the canonical ProofGraph projection;
8. verifies immutable analysis execution provenance;
9. captures verifier/runtime/code identities;
10. builds the deterministic verification identity;
11. appends the chained record transactionally;
12. saves with the existing guarded project-save precondition.

If the source project changes after the workflow ran, persistence fails rather
than attaching historical evidence to a different project revision.

## Historical immutability

Persisting a verification run appends a new record. It does not rewrite an
earlier verdict or update old evidence in place.

A later project edit produces a new project revision. A later verification run
is therefore bound to that new source revision and becomes a new ledger record.

Project loading and saving validate the verification ledger at the canonical
project boundary. Tampered record content, evidence digests, verification
digests, engineering identities, record hashes or chain links cause project
validation to fail closed.


## Operator CLI

Use the project verification command to produce and persist a new ledger record
from a saved project analysis:

```text
cleanroomx-project-verify persist project.cleanroomx.json <analysis-id>
```

A canonical FAIL or incomplete result is still persisted when the workflow itself
is valid; the command returns exit code 1 so CI/operator scripts can distinguish
that outcome from verified PASS (0) and operational/integrity failure (2).
