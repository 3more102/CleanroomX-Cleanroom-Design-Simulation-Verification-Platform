# Project requirements verification

Release 3 uses the persisted `project.metadata.requirements` registry as the
project-owned requirements authority. The verification engine in
`project_requirement_verification.py` is the first canonical
requirements -> evidence -> verdict slice.

It does not add standards limits, infer missing acceptance criteria, or duplicate
an engineering solver.

## Verification contract

Verification is explicit:

`requirement -> scoped entity -> bound engineering evidence -> comparison -> verdict`

Each evidence binding carries:

- stable evidence ID;
- requirement ID;
- entity/subject reference;
- engineering property name;
- value and unit;
- source and source revision;
- originating calculation when available;
- exact source/result locator when available;
- project revision when available;
- declared evidence kinds;
- freshness state.

Evidence freshness defaults to `unknown`, not `current`. The immutable-analysis
binding workflow derives freshness from the exact current analysis input and
live verification of the run's recorded external dependencies instead of
accepting a caller-supplied `current` assertion. The producing project
revision is retained separately as provenance.

## Comparison semantics

The engine derives comparison semantics only from the explicit persisted
criterion:

- `target` -> equality;
- `minimum` -> minimum bound;
- `maximum` -> maximum bound;
- `minimum + maximum` -> closed range;
- no criterion -> `not_checked`.

A requirement tolerance is an absolute tolerance. Missing tolerance means zero.
No relative tolerance or hidden engineering allowance is introduced.

For numeric equality, minimum, maximum and range checks, evidence must be finite.
For text/boolean equality, a non-zero numeric tolerance is invalid.

## Units

Release 3 routes numeric requirement comparisons through one centralized,
fail-closed engineering-unit authority whenever evidence and requirement units
use different explicitly registered spellings.

The registry is semantic, not merely dimensional. Current cleanroom/HVAC
families cover pressure, volumetric flow, inverse-time rates/ACH, temperature,
length, area, volume, velocity, power, mass flow, and humidity ratio. Common
explicit spellings such as `m3/s`/`m³/s`, `1/h`/`ACH`, and
`C`/`degC`/`°C` share canonical identities. Celsius/Fahrenheit/Kelvin
conversion is affine and is evaluated at full floating-point precision without
rounding before comparison.

The authority intentionally keeps semantically distinct quantities separate.
For example, `Hz` is a frequency family and is not interchangeable with
`1/h`/ACH even though both reduce dimensionally to inverse time. Unknown
spellings, named-unit versus unitless mismatches, and cross-family conversions
fail closed as `invalid`; the verifier never guesses engineering intent.

When conversion succeeds, `actual` and `delta` are expressed in the persisted
requirement unit before the requirement's absolute tolerance is applied. The
finding also retains `evidence_actual` and `evidence_unit` and records a
`unit_conversion` object containing the exact source/target spellings,
canonical units, semantic family, scale, offset, input value, and converted
output value. The original evidence document remains unchanged and stays bound
by evidence ID and digest.

Exact-unit comparisons retain the pre-conversion finding shape, preserving the
existing canonical result for projects that already use identical units.

## Evidence completeness and freshness

A PASS requires all of the following:

- requirement lifecycle status is explicitly `approved`;
- requirement applicability is explicitly `applicable`;
- exactly one authoritative evidence binding exists for the requirement/entity;
- evidence freshness is explicitly `current`;
- every `required_evidence` kind is present;
- evidence units match exactly or have an explicit compatible canonical conversion;
- the explicit criterion evaluates successfully.

The engine never chooses silently between multiple evidence values for one
requirement/entity binding. Ambiguity is `invalid`.

Stale evidence is surfaced as `stale` and is not used to issue PASS or FAIL.
Unknown freshness and missing required evidence are `incomplete`.

A requirement marked `not_applicable` is retained explicitly but excluded from
the active comparison set. `unknown` and `conditional` applicability remain
unresolved until another project workflow explicitly resolves them.

Lifecycle is also fail-closed. A `draft` requirement remains incomplete and
blocks a verified outcome. `superseded` and `withdrawn` requirements are
retained as explicit `inactive` findings but excluded from the active comparison
set. Evidence IDs are unique across the complete verification input so one audit
identity cannot resolve to multiple records.

## Truth states

Per-finding engineering state is richer than the existing aggregate verification
status:

- `pass`
- `fail`
- `not_checked`
- `stale`
- `incomplete`
- `invalid`
- `inactive`
- `not_applicable`

The aggregate result deliberately reuses CleanroomX's established truth model:

- `fail` when any included finding fails;
- `pass_with_unchecked` when PASS findings coexist with unresolved findings;
- `pass` only when all included findings are complete PASS results;
- `not_checked` when no included requirement has a checked result.

`verified=true` only when the aggregate is complete and `pass`.
`no_failures_detected=true` remains distinct from `verified=true`.

## Determinism and traceability

Equivalent engineering values are normalized before hashing, including numeric
integer/float spelling and signed zero.

The result exposes deterministic SHA-256 identities for:

- the normalized requirements registry;
- the normalized evidence collection;
- the complete verification result.

Evidence input order does not change the verification result or digest.

## Current boundary

This slice establishes canonical comparison semantics and evidence binding. It
does not yet:

- infer unregistered unit aliases or cross-family conversions;
- select solver outputs automatically;
- infer requirement-to-analysis mappings;
- generate ProofGraph records automatically;
- persist verification runs into project history;
- claim certification, commissioning/TAB acceptance, regulatory approval, or
  completeness of external standards.

Those integrations should consume this engine rather than reproduce its
comparison logic.
