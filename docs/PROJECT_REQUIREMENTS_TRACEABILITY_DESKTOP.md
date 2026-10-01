# Desktop requirements traceability review

Release 3 exposes the persisted project requirements registry and explicit
requirement-to-analysis evidence mappings in a read-only desktop review surface.

The viewer is intentionally an operator inspection layer. It does not edit
requirements, infer standards criteria, run analyses, recompute requirement
verdicts, convert units, or mutate persisted verification evidence.

## Authority boundary

The snapshot is built only from the canonical persisted parsers for:

- project requirements;
- requirement-to-analysis evidence mappings.

Before display, active mappings pass the same canonical cross-validation used by
project persistence. Invalid active references or analysis-kind mismatches fail
closed.

Historical disabled or superseded mappings remain visible. If an old analysis ID
is absent, the row is labeled `not_in_current_project`. If the ID now belongs to
another analysis kind, the row is labeled `kind_mismatch`; it is never silently
rebound to the new analysis.

## Desktop surface

Open **Analysis → Requirements Traceability...**.

The review shows:

- canonical requirements and mappings SHA-256 identities;
- deterministic registry and mapping counts;
- requirement lifecycle, applicability, scope, criterion, source, and evidence
  expectations;
- mapping lifecycle, requirement identity, analysis identity/kind state, subject,
  engineering property, exact result locator, unit, and evidence kinds.

This view is read-only and does not change solver equations, numerical
tolerances, convergence behavior, project schema, or engineering acceptance
semantics.
