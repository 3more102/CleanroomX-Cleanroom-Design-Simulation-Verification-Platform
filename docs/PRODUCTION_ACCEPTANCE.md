# Production Acceptance

CleanroomX uses an explicit production-acceptance gate in addition to the full test suite.

Run locally:

```bash
python scripts/production_acceptance.py --output production-acceptance.json
```

The generated JSON is deterministic repository-readiness evidence. CI publishes it from the **Production Acceptance** workflow and rejects the candidate if any required contract fails.

The gate covers release-evidence presence, development/release identity, source-versus-packaged demo synchronization, exact release dependency pins, immutable GitHub Action pins, the supported Python matrix, continuous hostile-input security checks, standards-source policy, and the engineering claim boundary. The same workflow reruns golden engineering references, persistence fault injection, packaging contracts, editor incident boundaries, security-policy regressions, and performance budgets.

A production candidate is accepted only when this named gate and the normal CI, Windows Standalone, Windows Installer Lifecycle, and Security workflows succeed for the same candidate SHA.

## What this gate does not claim

Production acceptance is software release evidence. It does **not** establish regulatory certification, ISO certification, commissioning/TAB acceptance, manufacturer approval, an independent penetration test, or independent CFD validation. Those require the corresponding external authority and project evidence.
