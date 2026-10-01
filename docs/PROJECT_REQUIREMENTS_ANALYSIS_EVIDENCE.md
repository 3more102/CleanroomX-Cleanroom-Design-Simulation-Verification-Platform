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

The caller supplies the current canonical input of the analysis and, for
file-backed analyses, the project/base directory used to resolve those external
references. The source project SHA-256 is retained as provenance, not used as a
coarse freshness switch.

Freshness is derived through the same Release 2 guards used by the desktop
application:

- exact current analysis input hash matches the immutable run input and every
  external dependency still matches its recorded content digest -> `current`;
- analysis input changed -> `stale`;
- an external dependency changed, disappeared, or cannot be proven current ->
  `stale`;
- current analysis input unavailable -> `unknown`.

This avoids invalidating engineering evidence merely because unrelated project
metadata or audit/run history was saved after the analysis. The caller does not
supply a free-form freshness label in this workflow.

The source project revision must be a lowercase SHA-256 identity and should come
from a trusted CleanroomX project revision boundary captured for execution. It is retained so the evidence can answer which project revision produced the run.

Project-bound execution paths, including the deterministic project batch runner,
now write the exact source project SHA-256 into application execution provenance.
Because that provenance sits inside the integrity-checked analysis-run bundle,
the evidence binder treats the embedded revision as authoritative and rejects a
conflicting caller-supplied revision. Legacy or direct unbound runs remain
supported only when the caller supplies a revision from a trusted CleanroomX
project execution/revision boundary.

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
- changed analysis input;
- changed, unavailable, or unverifiable external dependency;
- unavailable current analysis input;
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
