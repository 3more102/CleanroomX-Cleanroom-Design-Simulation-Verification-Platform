# First-class project requirements

Release 3 introduces a canonical persisted requirements registry at:

`project.metadata.requirements`

This is a project-data foundation. It does not add regulatory limits, reinterpret an external standard, or change any validated solver equation.

## Schema

The registry uses:

- `schema: cleanroomx.project-requirements`
- `schema_version: 1`
- deterministic `requirements_sha256` over the normalized registry body

Requirement sets and requirements are normalized by stable ID before hashing. Entity scope and required-evidence collections are also normalized because their order has no engineering meaning. Equivalent input ordering therefore produces the same normalized registry and digest; assumption order is preserved because narrative assumption sequencing can be intentional.

The SHA-256 value is an integrity/revision identity, not an authenticity signature.

## Requirement record

Each requirement carries explicit engineering identity and source context:

- stable `id`
- `title`
- `description`
- `discipline`
- `category`
- `source`
- `source_revision`
- optional clause/reference
- optional unit
- optional target
- optional minimum
- optional maximum
- optional non-negative absolute tolerance
- applicability
- project entity scope
- verification method
- required evidence kinds/labels
- lifecycle status
- assumptions
- notes

Numeric bounds must be finite and `minimum <= maximum`. A direct `target` cannot be combined with `minimum` or `maximum`; this prevents the later verifier from guessing between equality and bound semantics. Requirement IDs are unique across the complete project, not only inside one requirement set.

## Fail-closed semantics

Applicability defaults to `unknown`, not `applicable`.

Lifecycle status defaults to `draft`. Supported lifecycle states are:

- `draft`
- `approved`
- `superseded`
- `withdrawn`

These are requirement-record lifecycle states. They are not engineering verification verdicts.

A requirement may intentionally contain no numeric acceptance criterion. That allows narrative or future-mapped requirements to exist without CleanroomX inventing a comparison rule. A later verification engine must return an explicit unresolved/not-checked state when acceptance semantics are absent.

## Persistence boundary

When the requirements registry is present, normal project load/save validates and normalizes it through the same `cleanroomx.project` persistence boundary.

The project is rejected when the registry contains, for example:

- an unsupported schema version
- unknown requirement fields
- duplicate set IDs
- duplicate project-wide requirement IDs
- invalid/non-finite numeric criteria
- inverted minimum/maximum bounds
- negative tolerance
- invalid applicability or lifecycle state
- a mismatched supplied requirements digest

Projects with no requirements registry remain compatible with the existing project schema.

## Relationship to existing engineering workflows

The existing `design_requirements`, consistency, compliance rule-pack, and ProofGraph implementations remain canonical for their current calculations and evidence adapters. This Release 3 slice does not duplicate their solver/comparison logic.

The new persisted registry is the project-owned requirements authority that subsequent Release 3 work can map into:

`requirement -> applicable entity -> evidence -> comparison -> verdict -> ProofGraph`

That later mapping must remain explicit; this foundation does not silently convert room classifications, BIM properties, or external standards into acceptance criteria.


## Desktop traceability review

The desktop application exposes the persisted registry through
**Analysis → Requirements Traceability...**. The view is read-only, reports the
canonical registry SHA-256, and shows each requirement's set, lifecycle status,
applicability, scope, source revision, and explicit criterion. It does not edit or
infer requirements and it does not issue a verification verdict.
