# CleanroomX v0.100 Test Evidence

## Release candidate

Date: 2026-09-24

Release: **CleanroomX v0.100.0**

Canonical branch: `codex/cleanroomx-v0100-final-mainline`

The candidate is built directly from the integrated v0.99.1 mainline, not from an older divergent release branch.

## Required exact-head gates

Before merge, the exact pull-request head must pass:

- v0.91 selected-projection compatibility regressions;
- v0.92 full-bisection projection compatibility regressions;
- v0.93 supplied-point replay compatibility regressions;
- v0.94 canonical-provenance compatibility regressions;
- v0.95 solver-result-integrity compatibility regressions;
- focused v0.100 application, project-document, and GUI regressions;
- complete test suite on Python 3.11, 3.12, and 3.13;
- representative nonlinear loop, uncertainty, and dossier CLI JSON/Markdown smoke checks;
- clean-wheel build/install plus `cleanroomx-gui --check` on every Python matrix entry;
- installed-wheel packaged-demo verification;
- Python 3.13 real Tk/Xvfb `--demo --smoke`.

## v0.100 coverage

The candidate covers canonical application-input SHA-256 identity; before/after dependency SHA-256 and byte-size evidence; run-bundle export; catalog/mapping parity and pre-window registry validation; absolute-only unsaved dossier execution; portable consistency/dossier references across import and Save As; base-directory result-cache invalidation; abandoned-worker exclusivity; same-directory flush/fsync atomic project/export writes; user-visible export errors; and fan/system plot evidence.

## Verified predecessor evidence

The earlier integrated v0.99 baseline at commit `1f035d08f893573868610d35296e3947445318e6` passed GitHub Actions run id `36045911650` with 558 tests on each of Python 3.11, 3.12, and 3.13 plus the v0.91-v0.95 compatibility, CLI, headless-GUI, and Tk/Xvfb gates. Later v0.99.1 mainline work added the packaged demo, installed-wheel validation, and abandoned-worker exclusivity.

## Engineering boundary

Automated software validation is repository regression evidence. It does not establish ISO cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, physical/statistical uncertainty evidence, or regulatory compliance.
