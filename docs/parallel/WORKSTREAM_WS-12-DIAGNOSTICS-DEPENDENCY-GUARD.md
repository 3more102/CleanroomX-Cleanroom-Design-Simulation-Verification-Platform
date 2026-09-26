# CleanroomX Parallel Workstream Report

- Worker ID: `WS-12-DIAGNOSTICS-DEPENDENCY-GUARD`
- Branch: `dev/WS-12-DIAGNOSTICS-DEPENDENCY-GUARD`
- Repository main observed at session start: `2cccdbacff36e609cf9d39996cd36886bd574f35`
- Stacked starting SHA: `7277f20bdf86c65e549272151d17d3124daae302` (PR #497 source-project output guard)
- Finishing implementation SHA: `7870982f90a4b398d7fa1f74f7022f643d430e3b`
- Package version: `0.102.1`
- Assigned scope: protect project-diagnostics report export from overwriting declared external engineering input dependencies, without changing engineering calculations or schemas.

## Coordination history

This worker initially identified the retained run-history dependency-restoration defect independently and opened PR #499. During execution, PR #496 appeared with the same A→B→A retained-dependency fix and its own required parallel-workstream handoff. PR #499 was closed as a duplicate rather than creating competing integration work.

The unique implementation in this workstream is stacked on PR #497, whose CI-green change prevents `cleanroomx-project-check --output` from overwriting the checked source project itself.

## Defect fixed

The diagnostics CLI is intended to be a read-only project/model checker apart from its explicit report destination. Before this change, an operator could select an `--output` path that was also declared by a saved `consistency` or `dossier` analysis as an external engineering dependency. The atomic report writer would then replace that engineering input with diagnostics output.

CleanroomX portable-bundle export already protects its source project and packaged dependencies from destination collisions. The diagnostics CLI now applies the same input-protection principle.

## Implementation

- Reuses `cleanroomx.application._external_dependency_references` as the canonical enumeration of file-backed analysis references.
- Reuses `cleanroomx.application._resolve_relative` for project-relative dependency paths.
- Uses one alias predicate for resolved-path aliases and existing hard-link/file-identity aliases.
- Rejects report output that aliases the source project (inherited from PR #497) or any declared external dependency before diagnostics execution and before report publication.
- Error text identifies the protected dependency field and stable analysis id.
- Does not duplicate dependency-field schemas or modify any solver/model logic.

## Files intentionally modified

- `src/cleanroomx/project_diagnostics_cli.py`
- `tests/test_project_diagnostics.py`
- `docs/PROJECT_DIAGNOSTICS.md`
- `CHANGELOG.md`
- `docs/parallel/WORKSTREAM_WS-12-DIAGNOSTICS-DEPENDENCY-GUARD.md` (this report)

## Tests added

- `test_project_diagnostics_cli_refuses_to_overwrite_external_dependency`
  - builds a saved project with a real file-backed `consistency` analysis;
  - targets the referenced HVAC JSON as diagnostics `--output`;
  - requires exit code 2;
  - proves the dependency remains byte-for-byte unchanged.

## Baseline evidence

Repository `main` at `2cccdbacff36e609cf9d39996cd36886bd574f35` passed CI run `36195328839` / #1610:
- complete suite: **1043 passed** on Python 3.11, 3.12, and 3.13;
- Windows launcher smoke: successful.

The stacked base, PR #497 head `7277f20bdf86c65e549272151d17d3124daae302`, passed CI run `36228602682` / #1615:
- focused project diagnostics: **12 passed**;
- complete suite: **1044 passed** on Python 3.11, 3.12, and 3.13;
- Windows launcher smoke: successful.

## Post-change test evidence

PR #504 implementation head `7870982f90a4b398d7fa1f74f7022f643d430e3b` passed CI run `36229058810` / #1634:
- focused `tests/test_project_diagnostics.py`: **13 passed** on Python 3.11, 3.12, and 3.13;
- Python 3.11 full suite: **1045 passed in 107.25 s**;
- Python 3.12 full suite: **1045 passed in 120.90 s**;
- Python 3.13 full suite: **1045 passed in 100.33 s**;
- Windows launcher smoke: successful.

## Compatibility

- No project schema change.
- No diagnostics result schema change.
- No run-history schema change.
- No package/application version bump.
- No solver equation, numerical tolerance, convergence rule, unit, or engineering acceptance change.
- Existing valid distinct diagnostics output destinations behave as before.
- New behavior is fail-safe only when the requested report destination aliases protected project input.

## Shared interfaces changed

CLI behavior only: `cleanroomx-project-check --output` now rejects destinations that alias a declared external engineering dependency. No Python data-model/API contract is changed.

## Migration / schema changes

None.

## Known limitations

- The user's Windows `C:\\CleanroomX` filesystem is not mounted in this worker runtime, so local-only uncommitted changes, untracked files, and local/remote divergence could not be inspected. All implementation work is isolated on the GitHub branch above.
- The change protects file references represented by the canonical application dependency-reference contract. New future file-backed analysis kinds must register with that same authority to receive this protection, matching existing application/bundle behavior.

## Recommended integration order

1. Integrate PR #497 (source-project output protection).
2. Integrate/resolve the independent diagnostics freshness PR #496 as appropriate; it changes `project_diagnostics.py` and the shared diagnostics test/changelog files but not this CLI guard.
3. Retarget PR #504 to `main` after #497 lands, reconcile any shared test/changelog additions without dropping either worker's regression, and rerun focused diagnostics plus the full CI matrix.
