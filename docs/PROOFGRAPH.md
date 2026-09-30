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
Semantic cross-links fail closed as well: a finding must belong to the same
requirement as its referenced check, finding evidence must be declared by that
check, and every finding referenced by a verdict must belong to that verdict's
requirement.

Evidence provenance must remain acyclic. Multi-evidence dependency cycles such
as `A -> B -> A` are rejected so derivation lineage remains suitable for
deterministic traversal and audit. Cycle validation uses an explicit traversal
stack rather than Python recursion, so deep valid provenance chains are not
bounded by the interpreter recursion limit.

Verification runs are also closed over their declared checks: every verdict in
a run may depend only on findings whose compliance checks are listed in that
same run. This prevents a run from presenting a verdict derived from hidden or
out-of-run checks.

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

ProofGraph v1 uses six explicit verdict states:

- pass
- warning
- fail
- unknown
- indeterminate
- not_checked

Unknown is the fail-closed representation when the available evidence or
provenance is insufficient to issue a verified verdict. Indeterminate means the
canonical analysis was evaluated but its result interval overlaps the decision
boundary. not_checked means a known requirement/check was not evaluated by the
canonical source workflow, for example because required evidence is absent or an
explicitly optional mapping is not configured. None of these states is equivalent
to pass.

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

Existing not_checked findings remain not_checked in ProofGraph, and no evidence
record is fabricated for the absent value. This preserves the distinction between
a check that was not evaluated and a check whose evidence cannot support a
verified verdict.

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

not_checked remains not_checked in ProofGraph. A required missing mapping remains
fail, matching the source service. When no pressure target exists, the adapter
does not invent a requirement merely because a solved pressure observation is
available.

The design-requirements object, pressure-network object, and mapping policy each
receive deterministic revision digests. Confidence remains unset because the
canonical pressure consistency service does not itself provide a confidence
probability.


## IFC/BIM design-evidence integration

Verified normalized IFC semantics can now be converted into ProofGraph design
evidence with ifc_design_evidence_bundle, or attached immutably to an existing
graph with proofgraph_with_ifc_design_evidence.

The adapter re-normalizes the supplied semantic records and verifies any supplied
semantic SHA-256 before producing evidence. The caller must also provide the
explicit original IFC source filename and SHA-256.

Each normalized semantic field is retained as a separate DesignEvidence record
bound to the IFC GlobalId. Evidence keeps the semantic SHA-256 as its version and
the original IFC source digest as the evidence-source revision. Space
length/width/height evidence preserves the explicit dimension_source method, so
ifc_quantities and ifcopenshell_geometry remain distinguishable in the evidence
chain.

Storey identity, room containment links, placement coordinates, device
orientation, classification, and explicit CleanroomX space metadata remain
available as traceable design evidence without turning them into compliance
requirements automatically.

Attaching IFC evidence does not modify existing checks, findings, verdicts, or
verification runs. Later requirement integrations must explicitly reference the
IFC evidence they use.

## ACH design evidence integration

`proofgraph_from_ach_design` maps configured project minimum-ACH requirements to
traceable design-calculation evidence without introducing another airflow or ACH
solver. The adapter reuses the canonical preliminary `air_system_design` result
for governing supply airflow and the canonical `verify_room` path for room
volume, nominal supply ACH, and the configured minimum-ACH pass/fail semantics.

For each room with an explicit minimum ACH requirement it records:

- DesignEvidence for the configured minimum ACH and its requirement origin;
- DesignEvidence for requirement-side and air-system room dimensions;
- CalculationEvidence for room volume, governing design supply airflow, and
  nominal supply ACH;
- explicit upstream dependencies from room dimensions to volume and from volume
  plus governing supply airflow to calculated ACH;
- PASS/FAIL only when an exactly matched room has geometry established as
  consistent by the canonical design-consistency workflow.

A missing matching air-system room, missing usable calculation evidence, or a
room-geometry mismatch produces UNKNOWN rather than PASS. The existing
`design_consistency.ach_abs_tolerance_1_h` is not repurposed as a compliance
allowance: the canonical ACH verifier currently uses the exact project rule
`actual ACH >= configured minimum ACH`, so the ProofGraph criterion records a
zero ACH compliance tolerance.

This evidence remains a design/calculation layer. It is not commissioning,
operational, certification, or external-standard evidence.

## Airflow-balance evidence integration

`proofgraph_from_air_balance` maps the canonical steady-state room airflow
balance into ProofGraph without adding another balance equation. The adapter
retains explicit design inputs for supply, return, exhaust, transfer-in,
transfer-out, and minimum surplus, then reuses `calculate_air_balance` for net
surplus and surplus-margin calculation evidence.

The configured minimum surplus becomes the explicit project requirement. The
calculated net surplus is compared with that requirement using the canonical
`passes_minimum_surplus` result, and the signed surplus margin is retained as the
finding delta. Calculation provenance links the net-surplus result to all flow
inputs and links the final margin to both net surplus and the configured minimum.

This adapter intentionally does not infer leakage that was not modeled and does
not calculate or claim room pressure. The verification-run metadata preserves
that boundary explicitly.

## Thermal uncertainty capacity evidence integration

`proofgraph_from_thermal_uncertainty` bridges the canonical
`analyze_thermal_uncertainty` workflow into ProofGraph without duplicating
psychrometric, load, airflow, or capacity equations.

The adapter creates requirements only when an available cooling or heating
capacity is explicitly configured in the project input. Missing equipment
capacity therefore remains absent rather than becoming an invented requirement.

The evidence chain retains explicit uncertain inputs, fixed room/outdoor
air-state inputs, capacity margin, configured available capacity, internal and
makeup-air load intervals, net-load interval, sensible-load airflow interval,
governing airflow, and conservative cooling/heating capacity intervals. Derived
records link to their direct upstream evidence and identify
`analyze_thermal_uncertainty` as the originating calculation.

Canonical complete-interval semantics are preserved:

- PASS when the configured available capacity covers the full required interval;
- FAIL when the full required interval exceeds available capacity;
- INDETERMINATE when available capacity lies inside the required interval.

ProofGraph now accepts explicit `indeterminate` and `not_checked` verdict
states instead of forcing those conditions into PASS/FAIL. The thermal adapter
does not emit `not_checked` requirements for unconfigured capacities; it records
them as unconfigured in verification-run metadata.

Input provenance supplied through `UncertainValue` is retained as deterministic
evidence sources. Missing provenance remains visible in the canonical
traceability payload and is never converted into a confidence percentage.

If any canonical thermal input that participates in the traceability payload lacks
provenance, ProofGraph fails closed to UNKNOWN even when the underlying
engineering calculation returns PASS, FAIL, or INDETERMINATE. The canonical
thermal status remains in verification-run metadata so the engineering result is
not lost, but an unverifiable input chain is never promoted to a verified verdict.

This remains conservative engineering screening. It does not claim equipment
selection, hourly load simulation, statistical uncertainty, certification, or
any external standard requirement.
