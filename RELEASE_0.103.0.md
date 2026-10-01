# CleanroomX v0.103.0 Release Evidence

Release date: 2026-10-01

## Scope

CleanroomX v0.103.0 is the Release 3 verification, traceability, and evidence-integrity closure on top of the v0.102.1 spatial production baseline.

Release 3 includes:

- first-class persisted project requirements, explicit requirement-to-analysis evidence mappings, and fail-closed persisted evidence-authority decisions for ambiguous bindings;
- canonical requirements verification with deterministic engineering-unit conversion provenance;
- immutable, tamper-evident project verification history with present-currency assessment;
- ProofGraph projection, retained canonical evidence, cross-artifact integrity validation, and explicit evidence-precedence/conflict assessment;
- project-native verification, dossier, requirements-traceability, diagnostics, and verification-history operator surfaces;
- fail-closed external analysis-plugin trust controls;
- protected project-batch output publication that refuses to overwrite the source project, same-file aliases, or declared file-backed engineering dependencies, binds guard and execution to one loaded revision, and revalidates source/output identities immediately before publication;
- Python 3.11, 3.12, and 3.13 release gating plus Windows PowerShell/CMD launcher smoke.

## Verified functional baseline

PR #707 exact tested head:

`875408729ec3587d96f4c86f77b14de80b6548be`

CI run:

`36875375370`

Result:

- Python 3.11: 1662 passed, 4 skipped
- Python 3.12: 1662 passed, 4 skipped
- Python 3.13: 1662 passed, 4 skipped
- Windows launcher smoke: success

Subsequent Release 3 work adds ProofGraph evidence precedence/conflict assessment and CI hardening. The final v0.103.0 release candidate also consolidates persisted explicit evidence-authority decisions, the full protected project-batch publication race closure, and synchronized 0.103.0 package/runtime/demo identity. The PR #707 CI result above is therefore a verified functional baseline, not exact-head release evidence for the final candidate; the final candidate must pass its own complete exact-head CI gate.

## Final release authority

The final release commit is defined by the guarded publication workflow, not by a pre-written SHA in this document.

The publisher runs only after the repository CI workflow succeeds on `main`. Before creating `v0.103.0`, it verifies that:

1. the successful workflow head SHA is still the exact current `main` SHA;
2. `pyproject.toml` and `cleanroomx.__version__` are exactly `0.103.0`;
3. packaged and repository demo projects carry application version `0.103.0`;
4. the v0.103.0 changelog and this release-evidence document are present;
5. any pre-existing `v0.103.0` tag already points to that same commit.

The workflow never moves an existing release tag.

## Engineering boundary

The release-identity closure does not intentionally change solver equations, numerical tolerances, convergence rules, configured requirement criteria, project schema version, or historical verification verdict semantics.

CleanroomX remains an engineering screening, simulation, verification, and evidence platform; it does not by itself establish cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance.
