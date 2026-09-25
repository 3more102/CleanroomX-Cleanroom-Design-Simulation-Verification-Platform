# CleanroomX v0.100 Test Evidence

## Verified release baseline

Validation date: 2026-09-24

Merged release commit on `main`:

`fa02c71f990790089cb9c64eb2e009cd984eb5db`

Exact tested pull-request head:

`d8965090ee86713919079d9ee5e8a3b1d8f95e3b`

Pull request: **#242 — CleanroomX v0.100.0: final consolidated desktop release**

GitHub Actions CI:

- Run **#822**
- Run id: `36047808002`
- Conclusion: **success**

## Matrix evidence

The complete suite passed on every supported interpreter:

- Python 3.11: **576 passed**
- Python 3.12: **576 passed**
- Python 3.13: **576 passed**

The focused v0.100 application/project/GUI release gate also passed on all three interpreters, along with the dedicated v0.91, v0.92, v0.93, v0.94, and v0.95 compatibility gates.

## Packaging and desktop evidence

Every matrix job built CleanroomX **0.100.0** as a wheel, installed it into a clean virtual environment, ran the installed `cleanroomx-gui --check`, and verified the packaged demonstration resources.

Python 3.13 additionally passed:

- installed Tk/Xvfb `cleanroomx-gui --demo --smoke`;
- representative nonlinear loop, uncertainty, and dossier CLI JSON/Markdown smoke checks.

## v0.100 release scope verified by the focused gate

- application registry/catalog parity and fail-fast startup validation;
- canonical input SHA-256 execution provenance;
- before/after hash and byte-size evidence for external consistency/dossier dependencies;
- CLI-level failure injection proving consistency/dossier outputs are discarded when referenced inputs change during execution;
- run-bundle provenance export;
- portable consistency/dossier references across import and Save Project As;
- path-context cache invalidation;
- abandoned-worker exclusivity;
- durable same-directory atomic writes for project persistence and GUI exports;
- backend-derived fan/system plotting;
- bundled installed demo.

No validated solver equations, numerical tolerances, no-extrapolation/root-selection behavior, uncertainty semantics, or engineering acceptance criteria were intentionally changed by this release.
