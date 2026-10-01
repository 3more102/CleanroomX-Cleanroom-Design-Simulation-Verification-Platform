# CleanroomX v0.103.0 Release Evidence

## Release identity

- Release: **CleanroomX v0.103.0**
- Release line: **Release 3 — verification, traceability, and evidence-integrity closure**
- Release date: **2026-10-01**
- Supported Python: **3.11 / 3.12 / 3.13**
- Project schema remains **cleanroomx.project / version 1**

## Functional closure evidence

Release 3 functional closure was merged through PR #707.

- PR: **#707 — Release 3 final closure restack on current main**
- Exact tested PR head: `875408729ec3587d96f4c86f77b14de80b6548be`
- CI workflow run: **#2229 / 36875375370**
- Python 3.11: **PASS**
- Python 3.12: **PASS**
- Python 3.13: **PASS**
- Windows launcher smoke: **PASS**

The successful run included the focused Release 3 requirements/verification regression gate, the complete test suite, clean-wheel build/install checks, installed operator CLI checks, Release 2 performance evidence on Python 3.13, Linux Tk/Xvfb desktop smoke, real-widget spatial editing smoke, and Windows PowerShell/CMD launcher smoke.

## Release 3 closure scope

v0.103.0 closes the project requirements → evidence → verdict traceability line while preserving the validated solver and persistence foundations from earlier releases. The release includes:

- first-class persisted project requirements;
- explicit requirement-to-analysis evidence mappings;
- canonical requirement verification with deterministic engineering-unit conversion;
- explicit fail-closed evidence-authority handling for ambiguous bindings;
- persisted tamper-evident verification history;
- verification currency and dependency-freshness assessment;
- project-native verification, verification-history, dossier, and traceability operator surfaces;
- ProofGraph projection and cross-artifact integrity checks;
- qualification and recovery-test commissioning evidence bridges;
- retained canonical ProofGraph verification evidence;
- fail-closed external plugin trust controls;
- cooperative project-batch cancellation;
- desktop requirement/evidence/history review surfaces.

## Compatibility boundary

No solver equation, numerical tolerance, convergence rule, project schema version, configured requirement criterion, or historical verification verdict semantic is intentionally changed by the v0.103.0 release-identity closure.

## Immutable publication gate

The `v0.103.0` tag and GitHub Release are created only when:

1. repository CI completes successfully for the exact current `main` commit;
2. that same commit reports `0.103.0` in both `pyproject.toml` and `cleanroomx.__version__`;
3. shipped GUI demo project identities report `0.103.0`;
4. the v0.103.0 changelog and this release-evidence document are present;
5. `main` has not advanced between CI completion and publication.

If any condition is false, publication fails closed or is skipped rather than tagging stale code.

Historical v0.102.1 evidence remains preserved in `VALIDATION.txt`, `TEST_EVIDENCE.md`, and `ROLLBACK.md`.
