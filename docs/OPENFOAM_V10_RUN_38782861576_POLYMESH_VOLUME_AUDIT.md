# OpenFOAM Foundation v10 run 80: checkMesh/polyMesh volume reconciliation

## Provenance and execution

- Workflow: [Foundation v10 grid run 80](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38782861576), on code commit `eb6cde5789152b6b0191c499bb3b959a9fe725cd`.
- Solver: OpenFOAM Foundation v10, build `10-c4cf895ad8fa`.
- Evidence archive [11995514437](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38782861576/artifacts/11995514437), 11,914,406 bytes, SHA-256 `8bd5c2fd138c39ca8e836358cd622a6e13de4d2a24a7de16af1a7c32267cc839`.
- Nine synthetic cases completed 36/36 `blockMesh`, `checkMesh`, `simpleFoam`, and `foamToVTK` stages successfully and reached final time 150 s.
- Exact-head Required CI #4829 and CFD VTK Regression #475 passed.

The archive contains `poly_mesh_volume_audit.json`, SHA-256 `f519bde814ccb360d33b295110c1384448210ebf162e55712be829ad5de88515`. The report is bound to the exact manifest SHA-256 `3be0622ead4e52fd552d0229508438fb948430573645e2b473c340f3a46079e0` and execution-receipt SHA-256 `74b68d7bb429f6af245b46867b585ebd71a70bb2409f372b92c7288672f5756d`.

## Independent recheck

I independently recomputed every case with the current-head audit implementation. All 72 manifest file hashes, all 36 raw command-log hashes, nine receipt-bound `checkMesh` diagnostics, and all five raw `polyMesh` file digests per case matched. The recomputed audit objects matched all nine uploaded JSON records exactly.

For each case, `checkMesh` reports `Mesh OK.`; its parsed receipt is complete and bound to that raw log SHA-256. Each reconstructed total, `checkMesh` total, manifest-derived room volume, and mesh bounding-box volume is 12.0 m³. The bounding box is 3 m × 2 m × 2 m.

| Case | Cells | checkMesh min / max (m³) | Reconstructed min / max (m³) | checkMesh / polyMesh / room / bounding-box totals (m³) |
|---|---:|---:|---:|---|
| configuration_1/coarse | 216 | 0.05555555544 / 0.05555555578 | 0.05555555544444441 / 0.05555555577777785 | 12.0 / 12.0 / 12.0 / 12.0 |
| configuration_1/medium | 1,728 | 0.006944444389 / 0.006944444472 | 0.006944444388888871 / 0.006944444472222231 | 12.0 / 12.0 / 12.0 / 12.0 |
| configuration_1/fine | 13,824 | 0.0008680555486 / 0.0008680555694 | 0.0008680555486111091 / 0.0008680555694444487 | 12.0 / 12.0 / 12.0 / 12.0 |
| configuration_2/coarse | 216 | 0.05555555544 / 0.05555555578 | 0.05555555544444441 / 0.05555555577777785 | 12.0 / 12.0 / 12.0 / 12.0 |
| configuration_2/medium | 1,728 | 0.006944444389 / 0.006944444472 | 0.006944444388888871 / 0.006944444472222231 | 12.0 / 12.0 / 12.0 / 12.0 |
| configuration_2/fine | 13,824 | 0.0008680555486 / 0.0008680555694 | 0.0008680555486111091 / 0.0008680555694444487 | 12.0 / 12.0 / 12.0 / 12.0 |
| configuration_3/coarse | 216 | 0.05555555544 / 0.05555555578 | 0.05555555544444441 / 0.05555555577777785 | 12.0 / 12.0 / 12.0 / 12.0 |
| configuration_3/medium | 1,728 | 0.006944444389 / 0.006944444472 | 0.006944444388888871 / 0.006944444472222231 | 12.0 / 12.0 / 12.0 / 12.0 |
| configuration_3/fine | 13,824 | 0.0008680555486 / 0.0008680555694 | 0.0008680555486111091 / 0.0008680555694444487 | 12.0 / 12.0 / 12.0 / 12.0 |

## Tolerances and limits

The checkMesh decimal serialization half-step is inferred from the longest numeric token in its Min/Max/Total record: 10 significant digits. The reported-value comparison adds a binary64 arithmetic bound of `128 × epsilon × max(1, |value|)`; room-bound comparisons use the same scaled arithmetic bound. These are representation tolerances, not mesh-quality or CFD acceptance thresholds.

The maximum observed difference-to-allowed-bound ratio is 0.883858 (configuration_1/coarse minimum cell volume). All nine audit records remain `DIAGNOSTIC_ONLY`; scientific validation remains `BLOCKED`. The regular synthetic meshes do not establish project mesh quality, convergence, mesh independence, or physical cleanroom suitability.
