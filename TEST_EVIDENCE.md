# CleanroomX v0.99 Test Evidence

## Verified integrated baseline

Date: 2026-09-24

Integrated main commit immediately before the v0.99 metadata/documentation closure:

`9563507252f204bd8d88fa53f67d4afe2999f040`

GitHub Actions CI:

- Run #782
- Run id: `36045421373`
- Event: push to `main`
- Conclusion: **success**

## Matrix evidence

Run #782 executed the full suite on all supported Python versions:

- Python 3.11: **558 passed**
- Python 3.12: **558 passed**
- Python 3.13: **558 passed**

The workflow also completed the dedicated v0.91, v0.92, v0.93, v0.94, and v0.95 compatibility gates.

## Desktop and CLI evidence

On Python 3.13, run #782 additionally completed the installed `cleanroomx-gui --check` path, installed Tk/Xvfb, ran the real Tk GUI smoke against `examples/gui_demo.cleanroomx.json`, and completed the representative nonlinear loop/uncertainty/dossier CLI JSON/Markdown smoke checks.

The v0.99 final-release closure adds an explicit focused registry-integrity gate and changes release metadata/documentation only outside the version assertion/test expectation. Its pull request and the resulting `main` push are required to pass the same CI workflow before the release is considered closed.

## Engineering boundary

Passing automated tests establishes repository regression evidence for implemented software behavior. It is not evidence of ISO cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, physical/statistical uncertainty, or regulatory compliance.
