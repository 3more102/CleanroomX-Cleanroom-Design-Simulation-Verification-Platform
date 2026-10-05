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
