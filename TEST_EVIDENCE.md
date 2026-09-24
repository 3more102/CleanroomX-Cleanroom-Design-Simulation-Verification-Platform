# CleanroomX v0.100 Test Evidence

## Release candidate

Release line: **v0.100.0**

Canonical release branch: `codex/cleanroomx-v0100-final-consolidated`.

The branch is built from the v0.100 execution-integrity candidate on top of integrated v0.99 main, then consolidates the remaining independently-developed desktop/release deltas without changing validated engineering solver semantics.

## Required CI gates

The exact release head must pass:

- v0.91 selected-projection compatibility regressions;
- v0.92 full-bisection projection compatibility regressions;
- v0.93 supplied-point replay compatibility regressions;
- v0.94 canonical-provenance compatibility regressions;
- v0.95 solver-result-integrity compatibility regressions;
- focused application, project-document, and GUI release regressions;
- the complete test suite on Python 3.11, 3.12, and 3.13;
- representative CLI JSON and Markdown smoke checks;
- headless desktop registry readiness;
- real Tk/Xvfb desktop smoke;
- wheel build/install validation and packaged-demo smoke on Python 3.13.

## Consolidated v0.100 coverage

The release candidate adds regression coverage for application-input/dependency SHA-256 provenance, registry parity and fail-fast startup, absolute/relative dossier path rules, portable file-reference rebasing on import and Save As, cache invalidation on base-directory changes, abandoned-worker exclusivity, atomic project/export writes, run-bundle export, fan/system plot evidence, and packaged-demo completeness.

## Verified predecessor

Integrated v0.99 main commit `1f035d08f893573868610d35296e3947445318e6` previously passed GitHub Actions run id `36045390557` with 558 tests on each of Python 3.11, 3.12, and 3.13, plus CLI and Tk/Xvfb GUI smoke coverage.

## Engineering boundary

Automated software validation does not establish ISO cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, physical/statistical uncertainty evidence, or regulatory compliance.
