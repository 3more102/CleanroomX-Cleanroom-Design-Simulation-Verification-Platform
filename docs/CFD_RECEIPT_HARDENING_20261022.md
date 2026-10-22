# CFD run-receipt admission hardening — 22 October 2026

## Scope

The multizone computed-field importer now uses the existing strict JSON parser
for `run-receipt.json` instead of permissive `json.loads`. Duplicate JSON keys,
nonfinite constants, non-object roots and malformed stage structures are rejected
before accepting a solver run. Stage return codes must be actual integer zero
(not boolean or float zero), and the successful-stage failure field must be null.
Receipt/log/output SHA-256 comparisons remain mandatory.

## Reproduce the focused synthetic regression

```bash
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_cfd_receipt_integrity.py
```

These tests use constructed receipts and field/log text. They are NOT real
OpenFOAM runs and do not demonstrate convergence, grid independence, physical
particle transport, a 5 Pa closed-door cascade or cleanroom certification.

For an actual Foundation v10 multizone integration check on a properly equipped
Linux host:

```bash
bash scripts/with_openfoam10.sh python -m pytest -q tests/test_cfd_multizone_execution.py
```

## Engineering delivery gate

**HOLD** remains appropriate. Before physical or production sign-off, complete
a physically specified closed-door leakage and pressure-control model, assess
design-airflow numerical convergence and a mesh-independence study, verify the
Windows/WSL workstation bridge on its target system, and compare modeled
conditions against commissioning measurements. The frozen-field particle
screening is not a validated contamination/concentration transport model.

The hardening is defensive evidence handling, not new computational
fluid dynamics capability or a certification result.
