# Golden reference projects

CleanroomX keeps repository examples with explicit arithmetic and deterministic regression checks.
They are software-validation references, not universal cleanroom acceptance criteria.

## ROOM-A requirement-to-ProofGraph reference

`examples/golden_reference_room_ach.cleanroomx.json` validates the complete
requirement → analysis → evidence → verification → ProofGraph chain.

Known reference values:

- geometry: 6 m × 4 m × 3 m = 72 m³;
- supply airflow: 1,800 m³/h;
- air-change rate: 25 1/h;
- configured minimum: 20 1/h;
- expected verdict: pass.

`tests/test_golden_reference_project.py` also saves/reopens the project and proves
that the source revision, requirement/mapping hashes, verification hash, ProofGraph
hash, and workflow hash are repeatable.

## Multi-room facility reference

`examples/facility_project.json` and
`examples/consistency_hvac_demo.json` provide a second independent reference
covering room ACH, pressure cascade, cross-module airflow consistency, and
deterministic report generation.

Known room values:

| Room | Volume (m³) | Supply (m³/h) | ACH (1/h) |
| --- | ---: | ---: | ---: |
| Process | 90 | 2700 | 30 |
| Preparation | 60 | 1200 | 20 |
| Ante | 36 | 720 | 20 |

Known pressure-cascade values:

| Higher room | Lower room | Actual ΔP (Pa) | Minimum ΔP (Pa) | Expected |
| --- | --- | ---: | ---: | --- |
| Process | Preparation | 14 | 10 | pass |
| Preparation | Ante | 8 | 5 | pass |

The facility example deliberately leaves some per-room criteria unconfigured.
Its aggregate verification state is therefore `pass_with_unchecked`, not a
complete verified pass. This is intentional fail-closed behavior and is asserted
by `tests/test_golden_facility_reference.py`.

The paired HVAC example must produce three shared rooms, zero airflow mismatches,
and a deterministic cross-module consistency report.
