# CleanroomX v0.99 Test Evidence

## Verified release baseline

Date: 2026-09-24

Release baseline commit on `main`:

`1f035d08f893573868610d35296e3947445318e6`

GitHub Actions CI:

- Run #790
- Run id: `36045911650`
- Event: push to `main`
- Conclusion: **success**

## Matrix evidence

Run #790 executed the full suite on all supported Python versions:

- Python 3.11: **558 passed**
- Python 3.12: **558 passed**
- Python 3.13: **558 passed**

The workflow also completed the dedicated v0.91, v0.92, v0.93, v0.94, and v0.95 compatibility gates.

## Desktop and CLI evidence

On Python 3.13, run #790 also completed the installed `cleanroomx-gui --check` readiness path and the real Tk GUI smoke under Xvfb against `examples/gui_demo.cleanroomx.json`. Representative nonlinear loop, uncertainty, and dossier CLI JSON/Markdown smoke checks completed successfully.

The release baseline is package/runtime/demo/CI synchronized at `0.99.0`. The application registry rejects duplicate workflow keys, enforces ordinary parser/runner contracts and the custom consistency/dossier adapter contract, verifies declared callable bindings, and exposes structured readiness metadata through the headless GUI check.

## Release-document closure

The release-document pull request adds architecture, migration, security, deployment, rollback, test-evidence, and validation records only. It does not change runtime source, solver equations, numerical tolerances, uncertainty semantics, no-extrapolation behavior, or engineering acceptance rules. The documentation PR and resulting main push are required to pass CI before closure.

## Engineering boundary

Passing automated tests establishes repository regression evidence for implemented software behavior. It is not evidence of ISO cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, physical/statistical uncertainty, or regulatory compliance.
