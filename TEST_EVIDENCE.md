# CleanroomX v0.100 Release 2 Test Evidence

## Verified release baseline

Validation date: 2026-09-25

Exact tested and merged `main` commit:

`ec7b7a4e7f836159defa5591d396a951bfd5a3ba`

Release 2 integration history:

- PR **#414 — Release 2 architecture consolidation**, merged as `ae7297e229b51395f3bc278e9dab1e304517b84e`.
- PR **#421 — Release 2 final frozen candidate**, merged as `aed7d6a7e4970e20a9419b9cf0255171b521698a`.
- PR **#420 — Harden foundational numerical input integrity for Release 2**, merged as the tested `main` head above.

GitHub Actions CI:

- Run **#1431**
- Run id: `36143496033`
- Event: push to `main`
- Conclusion: **success**

## Matrix evidence

The complete suite passed on every supported interpreter:

- Python 3.11: **880 passed**
- Python 3.12: **880 passed**
- Python 3.13: **880 passed**

Each matrix job also passed the compatibility and release gates:

- v0.95 solver-result-integrity compatibility: **7 passed**
- v0.94 canonical solver-provenance compatibility: **5 passed**
- v0.93 supplied-point network-state replay compatibility: **10 passed**
- v0.92 compatibility: **15 passed**
- v0.91 compatibility: **8 passed**
- v0.100 application/desktop/input-contract/CLI gate: **211 passed**
- Release 2 consolidation gate: **128 passed**

## Packaging, CLI, desktop, and performance evidence

Every Python 3.11/3.12/3.13 matrix job:

- built the CleanroomX **0.100.0** wheel;
- installed that wheel into a clean virtual environment;
- passed installed `cleanroomx-gui --check`;
- verified the installed `cleanroomx-project-bundle` entry point;
- verified packaged demonstration resources;
- passed representative nonlinear loop, uncertainty, and dossier CLI JSON/Markdown smoke checks.

Python 3.13 additionally passed:

- Release 2 spatial-validation performance evidence;
- Release 2 project-bundle performance evidence, including the stress case with a 32 MiB dependency;
- installed Tk/Xvfb `cleanroomx-gui --demo --smoke`.

The project-bundle benchmark completed verification/export/extraction for small, medium, large, and stress cases. The stress case used a 33,554,432-byte dependency and completed without a validation failure.

## Release 2 scope covered by the verified tree

The tested tree includes the consolidated Release 2 architecture and later correctness hardening:

- isolated project-model snapshots and lossless same-schema extension preservation;
- stable analysis/spatial identity and strict project/spatial validation;
- durable verified atomic persistence and guarded project writes;
- session-isolated autosave, integrity-checked recovery, and protected legacy migration saves;
- bounded project/spatial undo-redo and guarded saved-project revision history;
- versioned analysis plugin API v1;
- isolated single-parse execution and immutable external-input/run evidence;
- persisted integrity-checked run history and dependency/staleness tracking;
- verified portable project bundles and self-contained engineering HTML reports;
- precision-safe HVAC/duct/branch/fan/thermal composition;
- explicit verification aggregate status/completeness;
- Markdown report-boundary escaping;
- finite-number validation at foundational engineering calculation boundaries.

The v0.91-v0.95 compatibility suites remain green on the same exact tree. The Release 2 work does not claim cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance; those remain external engineering responsibilities.
