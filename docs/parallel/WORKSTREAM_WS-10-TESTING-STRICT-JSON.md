# WORKSTREAM WS-10-TESTING-STRICT-JSON

- Worker ID: `WS-10-TESTING-STRICT-JSON`
- Branch: `dev/WS-10-TESTING-STRICT-JSON`
- Starting SHA: `2cccdbacff36e609cf9d39996cd36886bd574f35`
- Finishing implementation SHA: `e474b5cb68c7a7cae0aa3567e4ebd68ac9978f02`
- Assigned scope: harden strict JSON ingestion failure semantics and regression coverage only.

## Baseline

The worker runtime cannot access the user's local `C:\CleanroomX` filesystem, so no claims are made about local-only modifications. GitHub `main` was used as the available source of truth.

At the starting SHA, GitHub Actions CI was green:
- Python 3.11: 1043 passed.
- Python 3.12: 1043 passed.
- Python 3.13: 1043 passed.
- Windows launcher smoke: success.

## Files intentionally modified

- `src/cleanroomx/strict_json.py`
- `tests/test_strict_engineering_json_io.py`
- `docs/parallel/WORKSTREAM_WS-10-TESTING-STRICT-JSON.md`

## Completed

- Invalid UTF-8 in file-backed JSON is normalized to `StrictJSONError` with source-path context instead of leaking a raw `UnicodeDecodeError`.
- Excessive JSON nesting from either parsing or strict-clone validation is normalized to `StrictJSONError` instead of leaking `RecursionError`.
- Existing strict behavior for duplicate keys, non-finite numbers, unsupported Python values, and valid UTF-8 JSON is unchanged.

## Tests added

- Parameterized invalid UTF-8 regression across all 22 canonical file-backed engineering loaders.
- Excessive-nesting regression for `strict_json_loads`.
- New regression cases: 23.

## Compatibility

- No schema changes.
- No solver equations, tolerances, unit conventions, or acceptance criteria changed.
- Valid JSON inputs retain existing behavior.
- Exception normalization changes only malformed-input failure semantics.

## Shared interfaces changed

`load_strict_json` and `strict_json_loads` now guarantee `StrictJSONError` for invalid UTF-8 file content and recursion-depth failures.

## Migration/schema changes

None.

## Known limitations

- The worker runtime has no direct access to `C:\CleanroomX`; local working-tree status could not be inspected.
- Final branch validation is performed by GitHub Actions on the pull-request head. The PR checks are the authoritative post-change test evidence.

## Recommended integration order

This change is isolated to the canonical strict JSON boundary and its tests. It can be integrated independently after CI is green; if another worker changes `strict_json.py`, preserve both malformed-input contracts and rerun `tests/test_strict_engineering_json_io.py` plus the full suite.
