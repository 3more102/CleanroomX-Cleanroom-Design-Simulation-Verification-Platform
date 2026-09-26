# WORKSTREAM WS-11-AIR-BALANCE

## Identity

- Worker ID: `WS-11-AIR-BALANCE`
- Branch: `dev/WS-11-AIR-BALANCE`
- Starting SHA: `2cccdbacff36e609cf9d39996cd36886bd574f35`
- Finishing implementation SHA before this coordination artifact: `fe21bd8a7a665fc98c706e79a982f84db9d1a22d`
- Assigned scope: harden the preliminary `air_system_design` room air-balance sizing only, including its result evidence, Markdown report, regression coverage, and design-foundation documentation.

## Files intentionally modified

- `src/cleanroomx/air_system_design.py`
- `src/cleanroomx/design_report.py`
- `tests/test_air_system_design.py`
- `docs/DESIGN_FOUNDATION.md`
- `docs/parallel/WORKSTREAM_WS-11-AIR-BALANCE.md`

## Completed

- Added the explicit room air-balance supply requirement
  `max(0, exhaust + transfer_out + minimum_surplus - transfer_in)`.
- Included that requirement as a deterministic governing-airflow candidate.
- Removed the prior behavior that could clamp return to zero while publishing an achieved surplus below the configured minimum.
- Added scale-aware internal invariants for non-negative proposed return and minimum-surplus satisfaction.
- Added `airflow_drivers.air_balance` and `surplus_margin_m3_h` result evidence.
- Extended the Markdown design report with configured minimum, achieved surplus, and surplus margin.
- Preserved report replay compatibility for earlier result dictionaries that do not contain `surplus_margin_m3_h`.
- Documented the steady room balance and sizing assumption.

## Tests added / changed

`tests/test_air_system_design.py` now covers:

- existing strongest-driver behavior plus explicit balance-driver evidence;
- a balance requirement that governs supply and prevents a surplus shortfall;
- balance-only sizing with exhaust/transfer/surplus as the only airflow driver;
- Markdown exposure of minimum/achieved/margin surplus;
- replay of an older result without the additive `surplus_margin_m3_h` field;
- the no-driver case after explicitly zeroing all balance drivers.

## Test evidence

Baseline exact-main CI before modification:

- Main SHA: `2cccdbacff36e609cf9d39996cd36886bd574f35`
- GitHub Actions CI run: `36195328839`
- Python 3.11 complete suite: `1043 passed in 158.08s`
- Focused spatial gate: `63 passed`
- Project diagnostics gate: `11 passed`
- Application/desktop release gate: `298 passed`
- Release 2 consolidation gate: `132 passed`
- Python 3.11/3.12/3.13 jobs: success
- Windows launcher smoke: success
- Python 3.13 performance and installed GUI smoke: success

Final branch verification is owned by draft PR #500 and its GitHub Actions checks for the report-containing branch head. The PR must not be integrated unless those checks are successful.

## Engineering validation

The corrected sizing constraint follows the steady room airflow balance

`supply + transfer_in = return + exhaust + transfer_out + surplus`

with `return >= 0` and `surplus >= minimum_surplus`, giving

`supply >= exhaust + transfer_out + minimum_surplus - transfer_in`.

Regression case: 900 m^3/h exhaust + 200 m^3/h transfer-out + 100 m^3/h minimum surplus with zero transfer-in requires at least 1200 m^3/h supply. The previous post-selection clamp could publish only 720 m^3/h when ACH governed in that test configuration; the corrected balance driver selects 1200 m^3/h and produces exactly 100 m^3/h surplus with zero return.

## Shared interfaces changed

Result JSON is additively extended with:

- `rooms[*].airflow_drivers.air_balance`
- `rooms[*].surplus_margin_m3_h`

For previously infeasible cases, existing fields `governing_basis`, `governing_airflow_m3_h`, proposed return, and equipment counts can intentionally change because the configured balance requirement is now enforced.

No application registry, project persistence schema, or canonical spatial model was changed.

## Migration / compatibility

- Project schema: unchanged.
- Input contract: existing valid inputs remain valid.
- Persisted projects: no migration required.
- Historical result/report replay: preserved for results lacking the new surplus-margin field.

## Known limitations

This remains a preliminary steady airflow sizing workflow. It does not infer leakage coefficients, pressure-network operating points, TAB balancing, CFD performance, manufacturer curves, or regulatory acceptance. Pressure/leakage physics remain owned by the separate pressure-network workflow.

## Parallel integration safety

At final overlap review, active PRs #494-#499 modify packaging, strict JSON, project diagnostics, and project I/O. None modifies this workstream's production or test files.

Recommended integration order: independent of those workstreams; merge PR #500 only after its final CI is successful and after confirming `main` has not introduced a conflicting `air_system_design` or `design_report` change.
