# Project verification operator command

Release 3 exposes the canonical project requirements workflow as an operator CLI:

`cleanroomx-project-verify`

The command uses the existing saved-project requirements, explicit
requirement-to-result mappings, immutable analysis execution, canonical
requirements verifier, ProofGraph projection, and persisted verification ledger.
It does not introduce a second verification authority.

## Run without project mutation

```text
cleanroomx-project-verify run project.cleanroomx.json room-a
```

This prints the complete strict-JSON
`cleanroomx.project-requirements-workflow` artifact.

To publish it atomically:

```text
cleanroomx-project-verify run project.cleanroomx.json room-a --output workflow.json
```

Before writing a file, CleanroomX confirms that the saved project still matches
the exact source SHA-256 used for verification. The output destination is also
checked so it cannot replace the source project or a registered external
engineering dependency.

## Run and persist historical verification evidence

```text
cleanroomx-project-verify persist project.cleanroomx.json room-a
```

The command runs the same canonical workflow and then calls the guarded
verification-persistence boundary. Persistence succeeds only while the project
is still byte-for-byte the source revision used for the verification run.

The JSON response contains:

- source-project revision;
- selected analysis ID;
- canonical verification status/completeness;
- verification SHA-256;
- workflow SHA-256;
- complete persisted verification record;
- committed post-persistence project revision.

## Exit codes

- `0`: canonical verification is complete and verified PASS;
- `1`: the workflow executed successfully, but the canonical result is not a
  verified PASS (for example FAIL or incomplete/not-checked);
- `2`: operational/integrity failure, invalid project metadata, missing mapping,
  changed source revision, unsafe output path, or persistence failure.

A non-PASS verification can still be persisted. This is intentional: failed or
incomplete engineering verification is audit evidence and must not disappear
merely because the verdict is adverse.

## Desktop workflow

The desktop **Analysis** menu exposes the same canonical authorities:

- **Verify Project Requirements** runs the saved-project workflow read-only for
  the selected analysis.
- **Verify & Persist Project Requirements** runs the same workflow and appends
  the result to the guarded verification ledger.
- **Verification History...** opens the validated retained ledger and allows
  inspection of each complete persisted record.

Desktop verification requires a saved project with no unsaved edits and refuses
to run if the on-disk project revision no longer matches the revision currently
open in the application.

A valid FAIL or incomplete result is still persistable and is shown as requiring
attention rather than being discarded.

## Engineering boundary

This operator command does not infer requirements, units, evidence semantics, or
compliance. It invokes the same canonical workflow and verifier already used by
the project-native Release 3 architecture.

Persisted evidence remains historical and bound to its recorded source-project
revision. A later project edit requires a new verification run.
