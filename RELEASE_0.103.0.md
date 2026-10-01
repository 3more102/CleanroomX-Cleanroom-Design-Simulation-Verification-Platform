# CleanroomX v0.103.0 — Release 3 Production Closure

Date: 2026-10-01

## Final verified integration chain

| PR | Exact tested head | CI run | Result |
| --- | --- | --- | --- |
| #707 | `875408729ec3587d96f4c86f77b14de80b6548be` | `36875375370` | success |
| #709 | `aeccaca3fc7c3375acd5942e63d9b645a496d96c` | `36876575636` | success |
| #711 | `16e2ef204a55401e661720988f161b4b82b29f5c` | `36876866771` | success |
| #725 | `092ebbea37e33339fe0a1715789bb6aa74bf4d4c` | `36877833303` | success |

Final merged code baseline before release identity:
`a1499f59bbbd5f6d16fb9934218e60fe3c5fc669`.

PR #725's exact-head gate completed with **1675 passed, 4 skipped** on each
of Python 3.11, 3.12, and 3.13, plus successful Windows PowerShell/CMD launcher
smoke. The same gate also passed the v0.91–v0.95 compatibility checks, v0.100
application/desktop regressions, Release 2 consolidation regressions, Release 3
requirements/verification regressions, wheel/install checks, and representative
CLI checks.

## Release identity

The release-identity change sets package/runtime/demo identity to **0.103.0**,
promotes all Release 3 changelog entries, and adds a fail-closed publisher.
The publisher is eligible only after CI succeeds for a SHA that is still the
exact current `main` SHA. It refuses to move an existing `v0.103.0` tag.

## Engineering boundary

This release promotion intentionally changes no solver equation, numerical
tolerance, convergence rule, requirement acceptance criterion, project schema
version, unit convention, or historical verification verdict semantic.

Repository governance hardening is tracked separately in issue #519; it is not
an engineering-model or release-content change.
