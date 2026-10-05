# CleanroomX Production Acceptance Contract

This document defines the minimum release gates for a CleanroomX production candidate. It is an engineering software acceptance contract, not a claim of facility certification.

## Release identity

A production release must be tied to one **exact tested commit SHA**. The tree published as a release must be the same tree that passed the required release checks. Historical immutable release workflows remain SHA-pinned. Required CI, Security, and Production Acceptance gates use fixed runner labels, pinned GitHub Action revisions, and `pip==26.2.1` so release qualification does not silently move with floating CI toolchains.

## Required automated gates

A production candidate is acceptable only when all applicable checks below are green on the candidate tree:

1. **Core CI** — the complete suite passes on Python 3.11, 3.12, and 3.13, including compatibility, requirements, verification, persistence, recovery, reporting, and GUI regressions.
2. **Installed-artifact validation** — a clean wheel builds and installs, installed console entry points execute, the packaged demonstration resources exist, and the installed desktop GUI smoke test passes under a real Tk display.
3. **Golden engineering validation and evidence change control** — both the single-room requirement→evidence→verification→ProofGraph reference and the multi-room facility reference remain deterministic. Known ACH, pressure-cascade, and cross-module airflow results must remain within their explicit test tolerances. ProofGraph revision-diff/change-impact regressions must continue to flag unchanged downstream evidence and outcomes when their upstream source, evidence, or requirement revision changes.
4. **Performance budgets** — spatial validation and portable project-bundle stress benchmarks remain within the documented CI regression ceilings in docs/PERFORMANCE_GATES.md.
5. **Security** — the dedicated Security workflow passes the hostile-input/trust-boundary regression set and the prohibited-API static gate. Python and GitHub Actions dependency update automation remains configured.
6. **Persistence fault injection** — staged-write disk-full failure must not corrupt or partially replace an existing destination, a first project save must not publish a partial project, and generated-output failure must preserve the prior destination.
7. **Windows Standalone** — the Windows workstation build completes, smoke checks pass, and the release archive is emitted with SHA-256 evidence.
8. **Windows Installer Lifecycle** — the registered installer builds and the automated install, launch, upgrade, and uninstall lifecycle passes.

A release-blocking failure in any required gate must be resolved or explicitly removed from the claimed release scope before publication. Passing a subset of the matrix is not sufficient.

## Manual release review

Before release publication, the maintainer should also confirm:

- no known unresolved release-blocking P0/P1 defect remains in the intended release scope;
- release notes and known limitations match the exact candidate tree;
- schema/migration behavior is documented when applicable;
- generated engineering reports identify software/version provenance and do not overstate regulatory status;
- any externally supplied reference data used for validation has a recorded source and revision.

## Engineering and regulatory boundary

CleanroomX automated acceptance demonstrates software behavior against its defined tests and reference cases. It does **not** by itself establish CFD validation, cleanroom commissioning/TAB acceptance, manufacturer approval, accredited calibration, independent cybersecurity certification, or regulatory certification.

Those claims require the applicable external evidence, qualified personnel, controlled procedures, and jurisdiction-specific standards. CleanroomX should preserve traceability to such evidence when supplied; it must not manufacture or infer it.

## Change-control rule

If a change alters an engineering equation, tolerance, acceptance rule, project schema, evidence canonicalization, or release packaging contract, the corresponding reference case, documentation, and acceptance gate must change in the same reviewed change set. A test must not be weakened merely to make a regression green.
