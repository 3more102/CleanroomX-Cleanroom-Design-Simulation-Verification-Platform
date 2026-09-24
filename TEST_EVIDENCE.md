# CleanroomX v0.98 Test Evidence

## Verified main baseline

Date: 2026-09-24

Validated commit before this documentation-only release-hygiene change:

`d4fb2667afcff353d11cc50598366e6a9e24d08e`

GitHub Actions CI run:

- Run #774
- Run id: 36044748496
- Event: push to `main`
- Conclusion: success

## Matrix evidence

The release workflow executes on Python 3.11, 3.12, and 3.13.

For run #774 the complete pytest suite reported:

- Python 3.11: **556 passed**
- Python 3.12: **556 passed**
- Python 3.13: **556 passed**

The workflow also executes dedicated compatibility gates for v0.91, v0.92, v0.93, v0.94, and v0.95 before the complete suite.

## Application smoke evidence

On Python 3.13 the workflow additionally:

1. installs Xvfb and Tk;
2. runs `cleanroomx-gui --check`;
3. launches the installed desktop GUI under Xvfb;
4. loads `examples/gui_demo.cleanroomx.json`;
5. executes the active demonstration analysis through the real application path;
6. runs representative nonlinear loop, uncertainty, and dossier CLI JSON/Markdown smoke checks.

The same CI workflow also checks package/runtime version synchronization at `0.98.0` and verifies strict JSON serialization for representative outputs.

## Release PR evidence

The integrated v0.98 release was merged through PR #210 after its CI run #769 completed successfully. PR #210 is the implementation release line; this release-hygiene change adds documentation only and does not modify runtime source or tests.

## Engineering boundary

Passing automated tests establishes repository regression evidence for the implemented software behavior. It is not evidence of ISO cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance.
