# WORKSTREAM WS-11-PROJECT-IO

- **Worker ID:** WS-11-PROJECT-IO
- **Branch:** `dev/WS-11-PROJECT-IO`
- **Starting SHA:** `2cccdbacff36e609cf9d39996cd36886bd574f35`
- **Implementation/docs SHA before final coordination-report update:** `edb5ae5396e6f4007af13e3208e1b17dc337092b`
- **Assigned scope:** Harden project-file ingestion, persistence compatibility, and hostile/oversized project-data boundaries without changing engineering calculations.

## Files intentionally modified

- `src/cleanroomx/project.py`
- `src/cleanroomx/project_bundle.py`
- `src/cleanroomx/project_revisions.py`
- `tests/test_project_document.py`
- `tests/test_project_bundle.py`
- `tests/test_project_revisions.py`
- `SECURITY.md`
- `CHANGELOG.md`
- this coordination report

## Features completed

- Added a 64 MiB raw UTF-8 project-file ceiling before normal project parsing.
- Replaced unbounded normal project text reads with a bounded binary read plus a second post-read size check.
- Convert invalid UTF-8 normal project bytes into an actionable `ProjectFormatError`.
- Apply the same project limit before and during revision hashing, including a growth-after-`stat()` guard, while preserving the historical `OSError` contract used by batch/bundle source-stability checks.
- Refuse serialization of projects larger than the normal loader limit.
- Bound guarded-overwrite and revision-restore reads so a file that grows after revision capture cannot force an unbounded allocation.
- Apply the project ceiling to embedded portable-bundle project members before integrity hashing/allocation and at the project member reader.
- Bound saved project-revision envelopes to the maximum Base64-encoded project plus a fixed metadata allowance.
- Reject oversized declared revision sources before Base64 decoding and defensively bound decoded/restored project bytes.

## Tests added

Focused regressions cover:

- oversized normal project rejection before JSON parsing;
- exact-byte project boundary acceptance;
- oversized revision-capture rejection before hashing;
- file-growth rejection during bounded project reads and revision hashing;
- invalid UTF-8 project input;
- save/load size-limit symmetry;
- oversized bundled project manifest/member rejection;
- defensive bundle project reader limit;
- oversized revision-envelope rejection before JSON parsing;
- oversized declared revision source rejection before Base64 decode;
- defensive revision embedded-project byte limit.

## Tests run / baseline evidence

Before this branch, merged PR #493 head `fc3e3155e6c78bc3e44fe9ca8bd532a9164a8fa1` passed CI run #1609 on Python 3.11, 3.12, and 3.13 plus Windows launcher smoke. The Python 3.11 full suite reported **1043 passed**.

Final branch verification is delegated to the normal pull-request CI on draft PR #498 so the complete matrix, installed-wheel, GUI/CLI smoke, and compatibility gates execute against the integrated branch.

## Known limitations

- The 64 MiB ceiling is a deliberate project-artifact safety boundary, not a streaming JSON implementation.
- Recovery/autosave artifacts have their own format and lifecycle and were not changed in this workstream.
- No local `C:\CleanroomX` filesystem state was available to this worker; implementation and verification use the authoritative GitHub branch/CI path.

## Shared interfaces changed

- Added public module constant `cleanroomx.project.PROJECT_FILE_MAX_BYTES`.
- Existing loader/save function signatures and project schema remain unchanged.
- `capture_project_file_revision()` continues to surface file-access/revision-capture failures as `OSError` for compatibility with existing callers.

## Migration / schema changes

None. Project schema remains version 1. No project migration is required.

## Recommended integration order

Integrate after any concurrent changes touching `project.py`, `project_bundle.py`, or `project_revisions.py` are reconciled. Preserve the single `PROJECT_FILE_MAX_BYTES` authority and rerun the full PR CI after conflict resolution.
