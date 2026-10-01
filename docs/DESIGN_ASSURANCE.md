# Design Assurance Matrix

CleanroomX `design_assurance` is a read-only orchestration workflow that composes existing evidence-producing services:

1. one canonical `design_consistency` study;
2. optionally, one explicit `pressure_design_consistency` study; and
3. one or more versioned `compliance_check` rule-pack evaluations.

It does not introduce a new HVAC model, solver equation, standards limit, acceptance threshold, or implicit mapping between project terminology and external standards.

## Input

The workflow accepts exactly:

- `name`
- `design_consistency`
- optional `pressure_design_consistency`
- `compliance_checks`

The embedded design-consistency object is parsed by the canonical design-consistency parser. When present, the pressure-design-consistency object is parsed and executed by the canonical pressure-design-consistency service, including its explicit room → node/reference-node mappings and caller-supplied pressure tolerance. Every compliance object is parsed by the canonical compliance rule-pack parser. Unknown top-level fields are rejected.

At least one compliance check is required so the matrix represents both design consistency and declared project/standard evidence rather than acting as an alias for a single workflow.

## Result semantics

The matrix preserves the complete component results and adds only an aggregate view:

- `fail` if any included component records a failure;
- `not_checked` only when every component is entirely not checked;
- `pass_with_unchecked` when no component fails but unresolved evidence remains;
- `pass` only when every component is complete and passes.

The historical `passed` boolean remains a backward-compatible no-failure predicate, while `complete` indicates whether every included finding was evaluated. `no_failures_detected` exposes that no-failure meaning explicitly. `verified` is stricter and is true only when the matrix is complete and its aggregate status is `pass`; unresolved `not_checked` evidence therefore cannot be represented as fully verified.

## Traceability

Each compliance component retains its rule-pack identity, version, declared source, rule-pack SHA-256, exact evidence-document SHA-256, and a digest of the normalized component result. The design-consistency component retains the underlying requirement and preliminary air-system evidence produced by its canonical analysis together with a digest of that normalized result. When pressure-design consistency is supplied, the complete canonical pressure cross-check result is preserved as a separate component with its own normalized-result SHA-256; the pressure-network evidence, explicit mappings, tolerance, and source-analysis provenance therefore remain independently auditable rather than being flattened into the general consistency result.

The matrix also records `traceability_sha256`, a deterministic digest over the component traceability manifest. The matrix therefore provides a single audit artifact that binds criteria, evidence revisions, and normalized component results without flattening or rewriting the original evidence.

## Engineering boundary

A complete pass means only that all included CleanroomX design-consistency comparisons, optional explicit pressure-design comparisons, and supplied rule-pack checks completed without a recorded failure. It is not regulatory approval, cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or proof that a supplied rule pack completely represents an external standard.
