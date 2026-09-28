# Design Assurance Matrix

CleanroomX `design_assurance` is a read-only orchestration workflow that composes two existing evidence-producing services:

1. one canonical `design_consistency` study; and
2. one or more versioned `compliance_check` rule-pack evaluations.

It does not introduce a new HVAC model, solver equation, standards limit, acceptance threshold, or implicit mapping between project terminology and external standards.

## Input

The workflow accepts exactly:

- `name`
- `design_consistency`
- `compliance_checks`

The embedded design-consistency object is parsed by the canonical design-consistency parser. Every compliance object is parsed by the canonical compliance rule-pack parser. Unknown top-level fields are rejected.

At least one compliance check is required so the matrix represents both design consistency and declared project/standard evidence rather than acting as an alias for a single workflow.

## Result semantics

The matrix preserves the complete component results and adds only an aggregate view:

- `fail` if any included component records a failure;
- `not_checked` only when every component is entirely not checked;
- `pass_with_unchecked` when no component fails but unresolved evidence remains;
- `pass` only when every component is complete and passes.

The historical `passed` boolean remains a no-failure predicate, while `complete` indicates whether every included finding was evaluated.

## Traceability

Each compliance component retains its rule-pack identity, version, declared source, rule-pack SHA-256, exact evidence-document SHA-256, and a digest of the normalized component result. The design-consistency component retains the underlying requirement and preliminary air-system evidence produced by its canonical analysis together with a digest of that normalized result.

The matrix also records `traceability_sha256`, a deterministic digest over the component traceability manifest. The matrix therefore provides a single audit artifact that binds criteria, evidence revisions, and normalized component results without flattening or rewriting the original evidence.

## Engineering boundary

A complete pass means only that all included CleanroomX consistency comparisons and supplied rule-pack checks completed without a recorded failure. It is not regulatory approval, cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or proof that a supplied rule pack completely represents an external standard.
