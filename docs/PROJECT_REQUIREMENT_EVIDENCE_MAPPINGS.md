# Persisted requirement-to-analysis evidence mappings

Release 3 persists explicit project-owned mappings at:

`project.metadata.requirement_evidence_mappings`

The registry connects an existing project requirement to one existing project
analysis and one exact result path. It does not infer engineering semantics from
solver field names and it does not create acceptance criteria.

## Schema

The registry uses:

- schema: `cleanroomx.project-requirement-evidence-mappings`
- schema version: `1`
- deterministic `mappings_sha256`

Each mapping records:

- stable mapping ID;
- requirement ID;
- analysis ID;
- expected analysis kind;
- optional scoped subject/entity reference;
- explicit engineering property name;
- exact result path as object keys/list indexes;
- explicit unit when applicable;
- declared evidence-kind labels;
- lifecycle status;
- optional notes.

Mappings are normalized by stable mapping ID. Evidence-kind labels are treated as
a semantic set and canonicalized deterministically.

## Fail-closed rules

Active mappings are rejected when:

- a mapping ID is duplicated;
- two active mappings target the same requirement/subject pair;
- the requirement does not exist;
- the analysis does not exist;
- the stored expected analysis kind disagrees with the actual project analysis;
- a scoped requirement is mapped to a subject outside its declared scope;
- a project-scoped requirement is given an entity subject;
- the result path is empty, malformed, contains a negative index, or uses a
  boolean as an array index;
- unknown mapping fields are present;
- a supplied registry digest does not match normalized mapping content.

Disabled or superseded mappings may retain historical requirement/analysis
identities that are no longer active project objects. They are preserved for
traceability and are not silently rebound.

## Project persistence

The canonical `cleanroomx.project` load/save boundary normalizes this registry
without changing the outer project schema version.

A project containing active mappings is therefore internally cross-checked
against the same persisted requirements registry and analysis collection before
it is accepted or saved.

## Engineering authority

This registry is routing and provenance metadata only.

It does not:

- evaluate requirement criteria;
- convert units;
- infer which solver output should satisfy a requirement;
- reinterpret a result field;
- declare standards compliance;
- issue a verification verdict.

Requirement comparison remains exclusively in the canonical project
requirements verifier. Immutable analysis-run integrity and freshness remain
separate evidence-boundary responsibilities.

The next project-native orchestration layer can consume this persisted registry
to construct the already-existing immutable analysis -> evidence -> canonical
verification -> ProofGraph path without requiring callers to assemble transient
mapping objects manually.
