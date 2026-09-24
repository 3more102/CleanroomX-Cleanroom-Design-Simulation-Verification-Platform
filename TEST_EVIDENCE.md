# CleanroomX v0.99 Test Evidence

## Verified inherited baseline

Date: 2026-09-24.

The v0.98 integrated main baseline `d4fb2667afcff353d11cc50598366e6a9e24d08e` passed GitHub Actions CI run #774 on Python 3.11, 3.12, and 3.13. The complete suite reported 556 passing tests on each matrix job; Python 3.13 also passed the installed GUI check, real Tk/Xvfb smoke, and representative CLI smoke checks.

The application-registry hardening commit `40fc1694800088fc99731915e72a0a39d8cfa34e` passed CI run #775 before it was integrated to `main` through PR #213.

## v0.99 release candidate

This release adds version synchronization, abandoned-worker exclusivity, focused application/project/GUI lifecycle regressions, and release documentation. Its pull request must pass the full Python 3.11/3.12/3.13 CI matrix, v0.91-v0.95 compatibility gates, the complete suite, representative CLI smoke checks, and the Python 3.13 Tk/Xvfb GUI smoke before merge.

Final candidate run identifiers and pass counts are recorded in `VALIDATION.txt` after the passing release-candidate run.

## Engineering boundary

Passing automated tests establishes repository regression evidence for implemented software behavior. It is not evidence of ISO cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance.
