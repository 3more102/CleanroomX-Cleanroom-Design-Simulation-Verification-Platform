# CleanroomX v0.99 Test Evidence

## Verified integrated baseline

Date: 2026-09-24

Integrated release commit before the final abandoned-worker lifecycle hardening:

`1f035d08f893573868610d35296e3947445318e6`

Merged implementation PR: #217

GitHub Actions CI:
- Run #780
- Run id: 36045390557
- Conclusion: success

## Matrix evidence

Run #780 completed successfully on Python 3.11, 3.12, and 3.13. The complete suite reported **558 passed** on each interpreter. The workflow also passed the dedicated v0.91-v0.95 compatibility gates and representative nonlinear loop, uncertainty, and dossier CLI JSON/Markdown smoke checks.

On Python 3.13 the installed `cleanroomx-gui --check` readiness path and the real Tk GUI smoke under Xvfb also passed.

## Final lifecycle gate

The final release branch adds a regression that verifies **Abandon** does not re-enable the application until the abandoned backend worker exits. Its pull-request CI must pass the same Python 3.11/3.12/3.13 matrix, the dedicated lifecycle regression, the complete suite, CLI smoke checks, and the Python 3.13 GUI smoke before merge.

## Engineering boundary

Passing automated tests is software regression evidence. It is not ISO cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, physical/statistical uncertainty evidence, or regulatory compliance.
