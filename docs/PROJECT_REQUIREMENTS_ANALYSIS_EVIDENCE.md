# Project requirement evidence from immutable analysis runs

Release 3 can bind a verified CleanroomX analysis-run bundle directly to the
canonical project requirements verifier.

The purpose of this layer is to close the engineering chain:

`immutable analysis result -> explicit evidence mapping -> freshness -> requirement verdict -> ProofGraph`

It does not infer which result should satisfy a requirement and it does not add
standards criteria.

## Explicit mapping

Each `AnalysisRequirementEvidenceMapping` declares:

- stable evidence/mapping ID;
- target requirement ID;
- optional scoped project entity;
- engineering property name;
- exact path inside the analysis result;
- unit;
- evidence kind labels.

Result paths are typed tuples of object keys and non-negative list indexes.
They are rendered into an escaped `/result/...` locator for provenance. A
missing path produces an explicit missing value, which the canonical verifier
treats as incomplete evidence rather than PASS.

Mappings that resolve to arrays or objects are rejected because the current
requirement comparison engine accepts scalar engineering quantities only.

## Run integrity

Before any value is bound, the complete analysis-run bundle is validated with
CleanroomX's existing `verify_analysis_run_bundle` boundary.

Therefore a modified result, input snapshot, diagnostics record, or other
integrity-bound run content is rejected before it can become requirement
evidence.

The evidence source revision is the verified analysis-run bundle SHA-256.

## Freshness

The caller supplies the project content SHA-256 that was the source revision for
the run and, when available, the current project content SHA-256.

Freshness is derived as follows:

- matching source/current project revisions plus stable external dependencies -> `current`;
- changed project revision -> `stale`;
- unstable external dependencies -> `stale`;
- current project revision unavailable -> `unknown`.

The caller does not supply a free-form freshness label in this workflow.

Both project revision values must be lowercase SHA-256 identities.

The source project revision should come from a trusted CleanroomX project
revision boundary such as the project file revision captured for execution. The
analysis-run bundle itself does not independently prove which project file
revision launched it, so callers must not invent this value.

## Exact provenance

A bound evidence record preserves:

- verified analysis bundle SHA-256;
- project source revision;
- analysis kind and title;
- exact result locator;
- subject/entity reference;
- engineering property/value/unit;
- evidence kind labels.

The ProofGraph bridge uses the exact result locator as the evidence provenance
origin, so a displayed verdict can trace back to the precise field in the
immutable analysis result.

## Fail-closed behavior

This integration never converts these cases into PASS:

- run-bundle integrity failure;
- changed project revision;
- unstable external dependency;
- unknown current project revision;
- missing result path;
- non-scalar mapped result;
- missing required evidence kind;
- unit mismatch;
- missing requirement acceptance criterion.

The final comparison still occurs only in
`verify_project_requirements`; this binding layer does not reproduce criterion
logic.

## Direct ProofGraph workflow

`proofgraphs_from_project_requirements_analysis_run` performs the complete
deterministic path from an immutable run bundle through evidence binding,
canonical requirement verification, and the existing ProofGraph adapter.

It retains the same safety boundary: ProofGraph records the canonical verifier's
decision and does not re-evaluate or weaken it.
