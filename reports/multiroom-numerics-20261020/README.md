# Actual multiroom numerical review

These files record software execution and computed diagnostics. They do not
establish a commissioned cleanroom or a valid 5 Pa closed-door pressure cascade.

| Recorded case | Supply inputs (Process / Preparation / Ante), m³/h | Selected iteration | SIMPLE reported convergence | Sum of absolute cell flow imbalances, m³/s |
|---|---|---|---|---|
| `design-airflow` | 2700 / 1200 / 720 | 600 | No | 0.02614975417 |
| `low-flow-regression` | 2.7 / 1.2 / 0.72 | 163 | Yes, at 163 | 7.954936305e-11 |
| `low-flow-regression/earlier-iteration-50.json` | 2.7 / 1.2 / 0.72 | 50 | No for these fields; full run converged later | 4.008449682e-08 |

Both cases have 13,210 cells and one connected region. They use the existing
all-doors-open geometry, viscosity 1.5e-5 m²/s and explicit reporting density
1.2 kg/m³. The original design case remains unconverged. Reduced supply is a
deliberate numerical regression for testing the selected-iteration verdict;
its convergence cannot be transferred to the design-flow case.

The design case's net external imbalance is approximately 0.00010843052 m³/s,
while the sum of absolute cell imbalances is 0.02614975417 m³/s. A small net
boundary imbalance can therefore conceal larger local continuity errors.
No flow-balance acceptance threshold is assigned in these reports.

Each folder retains its exact manifest, execution receipt, computed summary
and four losslessly compressed stage logs. Decompress each `.log.gz` and compare
SHA-256 against the corresponding receipt stage. The manifest's hash also
matches the receipt. These hashes detect changes; they are not signed independent
attestations. Full field files are omitted and can be regenerated.

The PNG files are screenshots captured from the real Tk 8.6 review workspace:

- `actual-design-residual-review.png`: actual 600-iteration residuals and limits.
- `actual-room-flow-balances.png`: actual design-flow room/door results.
- `earlier-snapshot-convergence.png`: saved iteration 50 remains unconverged
  even though the same run subsequently converged at 163.
- `minimum-window-design.png`: actual design workspace after resizing to
  1050×680; door controls and the design body remain visible.

To reproduce the reduced-flow regression from the retained input:

```bash
bash scripts/with_openfoam10.sh cleanroomx-cfd-pipeline multizone-generate \
  reports/multiroom-numerics-20261020/low-flow-regression/project.json /tmp/cx-low-flow \
  --door-mode open --kinematic-viscosity-m2-s 1.5e-5 \
  --max-iterations 400 --output-interval 50
bash scripts/with_openfoam10.sh cleanroomx-cfd-pipeline multizone-run /tmp/cx-low-flow
bash scripts/with_openfoam10.sh cleanroomx-cfd-pipeline multizone-analyze /tmp/cx-low-flow \
  --density-kg-m3 1.2 --reference-room-id corridor --report-directory /tmp/cx-low-report
```

See `docs/MULTIROOM_CFD_EXECUTION.md` for scope, model limitations and the
ordinary design-flow reproduction commands. Numerical output and convergence
iteration can differ with the software environment.
