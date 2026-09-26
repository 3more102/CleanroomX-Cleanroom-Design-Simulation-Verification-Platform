# WORKSTREAM WS-14-PLUGIN-SAFETY

- **Worker ID:** WS-14-PLUGIN-SAFETY
- **Branch:** `dev/WS-14-PLUGIN-SAFETY`
- **Starting SHA:** `2cccdbacff36e609cf9d39996cd36886bd574f35`
- **Assigned scope:** Harden installed analysis-plugin discovery and registration failure containment only.

## Files intentionally modified

- `src/cleanroomx/plugins.py`
- `tests/test_plugins.py`
- `docs/PLUGINS.md`
- `SECURITY.md`
- `docs/parallel/WORKSTREAM_WS-14-PLUGIN-SAFETY.md`

## Features completed

- Isolate plugin-triggered `SystemExit` during discovery so one broken installed extension cannot terminate built-in application startup.
- Fail-isolate unreadable/invalid entry-point identity metadata while preserving deterministic diagnostics.
- Preserve `KeyboardInterrupt` as an operator cancellation signal rather than swallowing it as a plugin failure.
- Require plugin API versions to be real integers; reject Python boolean aliases.
- Reject leading/trailing whitespace in persistent plugin keys instead of silently normalizing project identity.
- Preserve existing plugin API version, application registry, execution path, result semantics, and provenance shape for valid plugins.

## Tests added

Focused regressions in `tests/test_plugins.py` cover:

- `SystemExit` isolation with continued discovery of a valid plugin;
- unreadable entry-point name isolation;
- `KeyboardInterrupt` propagation;
- boolean API-version rejection;
- plugin-key whitespace rejection.

## Baseline

Starting `main` SHA `2cccdbacff36e609cf9d39996cd36886bd574f35` has successful CI run `36195328839`. The same exact-main baseline is reported by concurrent PR #509 as **1043 passed** on Python 3.13.

## Validation

The local Windows checkout `C:\CleanroomX` is not mounted in this worker environment and outbound container DNS is disabled, so repository execution is delegated to the normal GitHub Actions pull-request matrix. Final CI evidence is recorded in the PR/workstream completion report.

## Known limitations

Plugins remain trusted in-process Python code and are not sandboxed. This workstream improves discovery/startup failure containment only; it does not attempt process isolation, publisher authentication, or permission mediation.

## Shared interfaces changed

No project schema, solver interface, numerical tolerance, application result schema, or plugin API version changed. Invalid plugin metadata that was previously silently normalized/reinterpreted now fails closed.

## Migration/schema changes

None.

## Recommended integration order

This branch is independent of the active thermal, CLI JSON, reporting, import/export, bundle, diagnostics, air-balance, and project-I/O workstreams. It can be integrated after CI passes; if `src/cleanroomx/plugins.py` or `tests/test_plugins.py` changes upstream, rebase/reconcile those files and rerun the full matrix before merge.
