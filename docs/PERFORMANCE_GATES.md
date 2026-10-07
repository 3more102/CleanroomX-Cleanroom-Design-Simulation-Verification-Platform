# Performance regression gates

CleanroomX runs deterministic synthetic performance checks in CI on Python 3.13.

These limits are **regression budgets**, not end-user workstation performance
guarantees. They are intentionally much looser than the measured hosted-runner
baseline so normal CI variance does not become a release failure.

## Spatial validation

The synthetic layouts contain:

- small: 100 rooms / 250 devices
- medium: 500 rooms / 1,250 devices
- large: 1,000 rooms / 2,500 devices

Public validation must complete within 0.10 s, 0.15 s, and 0.25 s respectively
on the CI runner. The large optimized overlap sweep must remain at least 2x
faster than the naive pairwise reference scan.

The validated 2026-10-05 Python 3.13 baseline was approximately 0.023 s for the
large public validation case and approximately 30.8x overlap-scan speedup.

## Project bundle stress

The stress case carries one 32 MiB engineering dependency through export,
inspection/verification, and extraction.

Each stress phase must complete within 3.0 s on the CI runner and the traced
Python peak must remain below 256 MiB. The extracted dependency must exist with
the exact original byte size and the verified dependency count must remain one.

The validated 2026-10-05 Python 3.13 baseline was approximately:

- export: 0.183 s
- verification: 0.097 s
- extraction: 0.183 s
- peak traced Python memory: 68 MiB

If a budget fails, investigate the regression instead of simply increasing the
limit. Change a budget only when the workload or accepted release envelope has
intentionally changed and new evidence justifies the new limit.

## ProofGraph change impact

`scripts/benchmark_proofgraph_change_impact.py` compares two revisions of
1,000-record and 5,000-record evidence chains serialized in reverse dependency
order. Only the root value changes; every unchanged downstream evidence record
must be flagged as potentially stale, with no extra direct evidence changes.

Each complete comparison must finish within 3.0 seconds. CI and Production
Acceptance both run this guard. Propagation indexes downstream dependencies once
and visits each impacted record once rather than repeatedly scanning the graph.

On Python 3.12.14 in the 2026-10-06 local validation environment, the 5,000-record
case fell from 8.370 seconds to 0.083 seconds. The complete comparison reports
retained identical SHA-256 identities before and after the optimization for both
workloads. These are synthetic regression measurements, not a comparison with
other engineering products or a workstation performance guarantee.
