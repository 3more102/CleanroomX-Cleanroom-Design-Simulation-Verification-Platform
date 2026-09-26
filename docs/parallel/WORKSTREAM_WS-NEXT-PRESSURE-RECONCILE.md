# WORKSTREAM WS-NEXT-PRESSURE-RECONCILE

- **Worker ID:** WS-NEXT-PRESSURE-RECONCILE
- **Branch:** `dev/WS-NEXT-PRESSURE-RECONCILE`
- **Starting main:** `2cccdbacff36e609cf9d39996cd36886bd574f35`
- **Canonical base implementation:** PR #511 head `c9388e8d3c7cbd53bade72210a382d4f485380c6`
- **Overlapping work reviewed:** PR #510 and PR #511

## Reconciliation

PR #511 is the canonical numerical-hardening base because it covers the broader
derived-state surface: mechanical-injection overflow, path-flow overflow,
Newton/Jacobian/elimination state, line-search rejection of non-finite trials,
target margins, totals, and report-unit conversions.

The following non-duplicated behavior from PR #510 is preserved on top:

- strict engineering scalar typing: booleans and numeric strings are rejected;
- explicit regression for overflow-safe initial fixed-pressure averaging;
- zero-flow dominant paths report `zero flow` instead of `inflow`.

The duplicate effective-pressure-overflow regression from PR #510 is not copied
verbatim because PR #511 already contains equivalent coverage for the same failure
boundary.

## Compatibility

No project schema, solver equation, convergence tolerance, result key, persistence
format, or normal-range engineering result is intentionally changed.
