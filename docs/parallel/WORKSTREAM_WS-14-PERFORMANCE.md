# Parallel Workstream Report — WS-14-PERFORMANCE

## Identity

- Worker ID: `WS-14-PERFORMANCE`
- Branch: `dev/WS-14-PERFORMANCE`
- Starting SHA: `2cccdbacff36e609cf9d39996cd36886bd574f35`
- Finishing implementation SHA: `87873fcc5d74e69d279174c02c70b8eab216520b`
- Assigned scope: improve spatial validation performance only, without changing project schema, engineering equations, spatial tolerances, warning semantics, or unrelated subsystems.
- Integration PR: #512 (draft)

The coordination-report commit itself follows the implementation SHA above and is documentation-only; use the current PR head as the final branch SHA.

## Files intentionally modified

- `src/cleanroomx/spatial.py`
- `tests/test_spatial.py`
- `scripts/benchmark_spatial_validation.py`
- `docs/parallel/WORKSTREAM_WS-14-PERFORMANCE.md`

## Completed

- Replaced per-room active-list rebuilds in `_room_overlap_records()` with deterministic heap-based expiry while retaining the exact overlap tolerance and final original-room ordering.
- Split validation into a private normalized-layout implementation plus the existing public `validate_layout()` compatibility wrapper.
- Changed the desktop workspace validation path to reuse its already-normalized canonical spatial layout instead of normalizing/copying it again after each validation-relevant edit.
- Extended the existing CI performance benchmark to measure normalized interactive validation separately from arbitrary-input public validation.

## Tests added

Three spatial regression tests were added:

1. optimized overlap sweep equals a naive pairwise reference on adversarial horizontal and vertical rectangle arrangements, including tolerance-boundary cases;
2. normalized validation output equals public `validate_layout()` output exactly for a layout containing duplicate names, overlap, opening errors, and an orphan device;
3. workspace validation does not call `normalize_layout()` again when validating canonical state.

## Test evidence

CI run `36231397266` at implementation SHA `87873fcc5d74e69d279174c02c70b8eab216520b`:

- Python 3.11: focused spatial gate `66 passed`; complete suite `1046 passed in 156.48s`.
- Python 3.12: focused spatial gate `66 passed`; complete suite `1046 passed in 173.83s`.
- Python 3.13: focused spatial gate `66 passed`; complete suite `1046 passed in 162.44s`.
- Windows PowerShell/CMD launcher smoke: success.
- Installed-wheel verification: success on the Linux test matrices.
- Python 3.13 installed desktop GUI smoke: `CleanroomX GUI smoke: PASS`.
- Compatibility/consolidation gates remained successful.

Python 3.13 spatial benchmark, 1,000 rooms / 2,500 devices:

- overlap sweep: `0.005442 s`;
- naive overlap reference: `0.151498 s`;
- normalized interactive validation: `0.006946 s`;
- public arbitrary-input validation: `0.024643 s`;
- overlap sweep/reference ratio reported by the benchmark: `27.84x`.

The same-run normalized interactive path is approximately 3.55x faster than the public compatibility path because it avoids a redundant full-layout normalization/copy.

## Shared interfaces changed

- No public API signature changed.
- `validate_layout(value)` retains its existing arbitrary-input normalization and output contract.
- One private helper, `_validate_normalized_layout(layout)`, was introduced for callers that already own canonical normalized state.
- No solver or persistence interface changed.

## Migration / schema impact

None. Project schema version, serialization fields, spatial layout version, unit conventions, engineering acceptance criteria, and numerical tolerances are unchanged.

## Known limitations

- The optimized normalized validation helper is intentionally private and assumes canonical normalized layout state. External/arbitrary input must continue through public `validate_layout()`.
- Heap expiry reduces broad-phase maintenance work, but exact overlap detection remains output-sensitive; pathological layouts where many rooms mutually overlap still require pairwise exact checks among active candidates.
- The worker could not inspect the user's Windows `C:\CleanroomX` working tree from this chat. GitHub `main` and the isolated branch were used as the accessible source of truth; no local user checkout was reset or modified.

## Recommended integration order

This workstream is independent of solver, reporting, import/export, diagnostics, and project-I/O workstreams. Integrate after any concurrent spatial edits have been checked for overlap with `src/cleanroomx/spatial.py`; otherwise it can be merged independently after normal PR review and green CI.
