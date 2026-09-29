# ProofGraph foundation

CleanroomX ProofGraph is the GUI-independent evidence model for the continuous
compliance digital-twin direction. It is intentionally a data and traceability
foundation, not a second engineering solver.

## Schema

The first serialized schema is:

- schema: cleanroomx.proofgraph
- schema version: 1
- deterministic canonical SHA-256 over the complete graph body

A parsed document with a supplied graph digest is rejected if the digest does not
match the normalized graph content.

## Core objects

The foundation defines typed records for:

- Requirement and RequirementSet
- EvidenceSource and Evidence
- DesignEvidence
- CalculationEvidence
- SimulationEvidence
- CommissioningEvidence
- OperationalEvidence
- ProvenanceRecord
- ConfidenceRecord
- ComplianceCheck
- ComplianceFinding
- ComplianceVerdict
- CorrectiveAction
- VerificationRun
- ProofGraph

The graph validates references between requirements, evidence, findings, verdicts,
corrective actions, and verification runs. Dangling references fail closed.

## Evidence layers

Evidence keeps its layer instead of overwriting earlier values. Design,
calculation, simulation, commissioning, and operational evidence can therefore
coexist for the same engineering property in later integration slices.

The generic declared evidence kind is reserved for evidence whose lifecycle layer
is not known. The existing compliance rule-pack adapter deliberately uses
declared rather than guessing that an arbitrary supplied evidence document is
design, commissioning, or operational data.

Each evidence record can retain:

- source identity and source revision
- project and subject references
- property/value and engineering unit
- optional external timestamp
- provenance records
- IFC GlobalId
- CleanroomX entity identity
- originating file or calculation
- upstream evidence dependencies
- confidence and uncertainty metadata

Confidence is optional. ProofGraph does not manufacture a confidence percentage
when none exists in the underlying engineering evidence.

## Compliance states

ProofGraph v1 uses four explicit verdict states:

- pass
- warning
- fail
- unknown

Unknown is the fail-closed representation for insufficient or unavailable
evidence. It is not equivalent to pass.

## Existing rule-pack bridge

proofgraph_from_compliance_check converts the existing deterministic
compliance-rule-pack evaluation into the ProofGraph structure without changing
the rule engine.

The adapter preserves:

- rule-pack identity and version
- declared source/reference
- operator and expected value
- evidence path
- unit and tolerance
- supplied evidence revision SHA-256
- actual evaluated value
- delta
- pass/fail result
- missing-evidence state

Existing not_checked findings become ProofGraph unknown verdicts and no evidence
record is fabricated for the absent value.

This is an adapter boundary. It does not reinterpret an external standard, invent
a standard limit, or claim that the supplied rule pack is complete.

## Corrective-action safety

CorrectiveAction is modeled now so later deterministic remediation work has a
stable audit shape. A ProofGraph corrective action must retain
requires_approval=true. This foundation never applies a proposed engineering
change automatically.

## Serialization boundary

proofgraph_from_dict performs strict schema parsing:

- unknown fields are rejected
- non-finite JSON numeric values are rejected
- duplicate identifiers are rejected
- unsupported evidence/verdict kinds are rejected
- cross-record references are validated
- an included graph SHA-256 must match the reconstructed graph

The model remains pure Python with no GUI dependency.

## Next integration slices

The next high-value work should build on this model rather than create another
parallel evidence representation:

1. emit CalculationEvidence from existing pressure, airflow, ACH, and spatial
   design analyses;
2. emit DesignEvidence and ProvenanceRecord data from IFC semantic bindings,
   including dimension_source, GlobalId, storey, placement, and source digest;
3. add explicit evidence precedence/conflict policies without deleting history;
4. expose requirement -> evidence -> verdict drill-down in the desktop
   Compliance / Assurance area;
5. add commissioning and operational adapters only after their source identity,
   freshness, and uncertainty contracts are explicit.

ProofGraph does not itself establish regulatory approval, cleanroom
certification, commissioning acceptance, or completeness of an external
standard.


## Pressure design evidence integration

The pressure-design adapter is the first direct engineering-to-ProofGraph bridge.
proofgraph_from_pressure_design_consistency reuses the canonical
pressure_design_consistency service and does not solve pressure through a second
path.

For each configured room pressure target it creates:

- a Requirement retaining the explicit target, tolerance, and room/node/reference
  mapping;
- DesignEvidence for the configured pressure_target_pa and its design-requirement
  origin;
- CalculationEvidence for the solved signed node-to-reference pressure difference
  when that calculation exists;
- a ComplianceCheck requiring both design and calculation evidence;
- a finding and verdict that preserve the canonical pass/fail/not_checked result.

not_checked maps to ProofGraph unknown. A required missing mapping remains fail,
matching the source service. When no pressure target exists, the adapter does not
invent a requirement merely because a solved pressure observation is available.

The design-requirements object, pressure-network object, and mapping policy each
receive deterministic revision digests. Confidence remains unset because the
canonical pressure consistency service does not itself provide a confidence
probability.
