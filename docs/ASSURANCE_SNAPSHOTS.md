# Design Assurance Snapshots

`cleanroomx-assurance-snapshot` creates deterministic, self-contained audit artifacts from the existing `design_assurance` workflow. The snapshot freezes the exact UTF-8 source bytes, the normalized CleanroomX result, the result digest, the design-assurance traceability digest, and the CleanroomX version that produced the artifact.

The feature is a provenance and replay layer only. It does not add engineering equations, standards limits, acceptance thresholds, certification semantics, or hidden mappings.

## Snapshot format

Schema v1 is `cleanroomx.design-assurance-snapshot`.

Each snapshot contains:

- the exact source text, byte size, and SHA-256 of the supplied design-assurance input;
- the full normalized design-assurance result;
- the canonical SHA-256 of that result;
- the design-assurance `traceability_sha256` that already binds component results, rule-pack revisions, and supplied evidence revisions;
- the CleanroomX version used to create the snapshot;
- one canonical snapshot SHA-256 over every field above.

No creation timestamp or machine-specific path is included, so identical source bytes analyzed by the same CleanroomX build produce identical snapshot content.

Canonical JSON hashing uses sorted keys, compact separators, UTF-8, strict finite JSON values, and no ASCII-only rewriting.

## Creation

```bash
cleanroomx-assurance-snapshot create examples/design_assurance_demo.json design_assurance.snapshot.json
```

Creation fails closed when:

- the input is not stable while it is being read;
- the input exceeds 16 MiB;
- the input is not valid UTF-8 strict JSON;
- duplicate JSON object keys or non-finite JSON values are present;
- the design-assurance parser rejects the input;
- the output aliases the source path;
- atomic persistence cannot be completed and verified.

## Verification

```bash
cleanroomx-assurance-snapshot verify design_assurance.snapshot.json
```

Verification independently checks:

1. schema, version, canonicalization, and exact v1 field set;
2. embedded source byte count and SHA-256;
3. embedded result SHA-256;
4. the stored design-assurance traceability digest;
5. the overall snapshot SHA-256;
6. deterministic replay of the embedded source through the current canonical design-assurance parser and engine;
7. equality of the replayed result, result digest, and traceability digest.

A valid verification report exposes both `integrity_valid` and `replay_consistent`. The CLI exits `0` only when both are true. A structurally valid but tampered snapshot returns an `invalid` report and exit code `2`; malformed or unsupported snapshots also exit `2` with an error.

The verification report records both the snapshot's producing CleanroomX version and the current verifier version. A version difference is visible as `version_match: false`; it is not silently hidden. Replay must still match for the snapshot to be reported valid.

## Security and limits

Snapshot files are capped at 64 MiB before parsing. Embedded design-assurance source content must still fit the 16 MiB input limit. Verification never executes embedded code, follows paths, or loads external files; it replays only the embedded strict-JSON design-assurance object through the existing pure analysis service.

Snapshot SHA-256 values are deterministic content identities, not digital signatures. They detect content modification but do not establish who created or approved the file.

## Engineering boundary

A valid snapshot proves only that the embedded bytes, normalized result, traceability evidence, and deterministic replay agree under the verifier. It does not establish signer identity, source authenticity, completeness or correctness of a supplied rule pack, regulatory approval, cleanroom certification, CFD validation, manufacturer approval, or commissioning/TAB acceptance.
