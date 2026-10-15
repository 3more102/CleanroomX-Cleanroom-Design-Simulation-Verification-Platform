# OpenFOAM Foundation v10 run 58: native `U` to VTK parity

## Provenance

- Workflow: [OpenFOAM Foundation v10 grid run 58](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38694132081)
- Code revision: `66152ee3e0c9a89d7cac1bbddb85e38a94cb93e8`
- Runtime: OpenFOAM Foundation v10, build `10-c4cf895ad8fa`
- Artifact: [run 58 evidence archive](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38694132081/artifacts/11953511345)
- Artifact SHA-256: `53d965e3facdc1bb06930b6e73f48230e627632d92e85bdfd21526e5319e47af`
- Artifact archive size: 10,516,659 bytes

The workflow executed nine explicitly synthetic cases (three layouts by three grid levels), with 36/36 command stages returning zero. Each case reached time `150s`; `checkMesh` reported `Mesh OK.`. The archive contains the generated manifest and dictionaries, native OpenFOAM fields, `phi`, solver logs, VTK outputs, execution receipts, and triage reports.

## Field-parity method and result

The workflow ran `foamToVTK -latestTime -fields '( U )' -ascii -poly -noPointValues`. For each case it compared the final-time native ASCII `volVectorField` at `150/U` with the VTK cell-data `U` array. The `cellID` array established a complete, unique mapping from each VTK cell to its native mesh cell; array order was not assumed. All three velocity components were compared for every cell.

Foundation v10 exports the legacy VTK `U` array as float32. The recorded bound accounts for binary32 rounding of the field and VTK reader plus half a unit in the last place at six significant decimal digits. This is an output-serialization bound, not a solver or engineering acceptance threshold.

| Case | Cells | Components compared | Maximum absolute error (m/s) | Serialization bound (m/s) | Maximum relative error |
|---|---:|---:|---:|---:|---:|
| configuration_1/coarse | 216 | 648 | 4.91466455088e-7 | 5.14901161194e-7 | 4.58061013699e-6 |
| configuration_1/medium | 1,728 | 5,184 | 5.07119450377e-7 | 5.14901161194e-7 | 4.85910562735e-6 |
| configuration_1/fine | 13,824 | 41,472 | 5.12711003126e-7 | 5.14901161194e-7 | 5.02477017084e-6 |
| configuration_2/coarse | 216 | 648 | 5.28882292128e-8 | 5.74505805969e-8 | 4.77325033617e-6 |
| configuration_2/medium | 1,728 | 5,184 | 5.53791946467e-8 | 5.74505805969e-8 | 4.89856409189e-6 |
| configuration_2/fine | 13,824 | 41,472 | 5.57159715309e-8 | 5.74505805969e-8 | 4.97886103871e-6 |
| configuration_3/coarse | 216 | 648 | 5.06185972200e-8 | 5.74505805969e-8 | 4.94329434622e-6 |
| configuration_3/medium | 1,728 | 5,184 | 5.56442099064e-8 | 5.74505805969e-8 | 4.89095995676e-6 |
| configuration_3/fine | 13,824 | 41,472 | 5.58776696719e-8 | 5.74505805969e-8 | 5.02888377751e-6 |

**Result:** 9/9 cases passed; 47,304 cells and 141,912 velocity components were compared. The maximum absolute error was `5.12711003126e-7 m/s`, below that case's `5.14901161194e-7 m/s` serialization bound.

| Case | Native final-time `U` SHA-256 | VTK dataset SHA-256 |
|---|---|---|
| configuration_1/coarse | `d440f1b54752f64b8474b296c3966f1bf56ba66efba0054fce6fd3634fc8bebb` | `c30f14a36d177b4b58dd79714902a42905f14b5d813360a38ad398907806ef0d` |
| configuration_1/medium | `68bd021b08d3d49e1d982c03493f2fff864270fcbc6df6997213d933bc7dc959` | `340aa0f3f291a260bcb706340aa76b32595160caf3a0a99c2899d901bca9352d` |
| configuration_1/fine | `c2ad0dc3a570b5d2e805fe21c9eb0545635ce505b5f29269e83ae4647593fc98` | `0c269a6f806ba56234a533a7fd05f54ba132d7aa5d50c60a332697f2d9f700f3` |
| configuration_2/coarse | `814bfeccd4a2c230e841e6f55e551cc7fe0062ad3c82382cfebffa2f1dd57f68` | `fa22aebd3a7e7ff4fe3fd4ca99e3995151bbd8abe7929f6ddca633df0e65f297` |
| configuration_2/medium | `47344bc45cc4b07de73cd4120dc1e9dd9322c23f124812775a63319c98fba3ab` | `f7e96e80254e2c5d83d78bb0e43a7cdcfda753550562f885f4d72624d7f55f05` |
| configuration_2/fine | `cf37dd35b6d2200fa7e1b0b3e544d720aac326721f61e11f889f90358d5533e0` | `f5304b551370171ce906816c7c7ca4c66be830a19427c8f135c538294fc5263c` |
| configuration_3/coarse | `221dab422037be5cda0bd0e149675160899635b8858ee89c5794b8e75eac3cb9` | `db3b8b1e7d4e094e013a920e756a58e969daf40f69fa1a7baee6e84b69622d99` |
| configuration_3/medium | `873f478a3ce7bdd1bc0562aafa2906786a047bcc48fd735255255d6886c888dd` | `4213fad15ff7deee69e201667635f0064ae3521015ecdd5d82d152210d44d0d8` |
| configuration_3/fine | `93a8c20dcf17affd5a3f7da1b9eec4a624b70739f6ff8a2af8ff15df0ee8e409` | `d9105f06de103b698bfc8588eff1aba625fe9a71f168704be9236b3f3a83759b` |

After downloading the archive, its SHA-256 and all 18 native/VTK file digests were independently checked. Re-running CleanroomX's parity audit on the archived files reproduced each of the nine recorded parity results exactly.

## Remaining engineering and scientific limits

- This is synthetic execution evidence. The generated model is an empty rectangular room without an underfloor plenum, turbulence or buoyancy, scalar/particle transport, or physical measurement inputs.
- All nine cases remain `DIAGNOSTIC_ONLY`. The logged terminal residual-control screen reports both `U` and `p` above their configured tolerances in every case. The `U` residual ratios span about `521.95×` to `174,725.41×`; the `p` ratios span about `446.26×` to `25,911.71×`.
- Measured final-time flux imbalance spans `0.005341%` to `0.187145%`; no project acceptance criterion is defined. Configuration 1 has reverse flow at the pressure outlet on all three grid levels.
- VTK field parity establishes correspondence and serialization agreement for these generated fields. It does not establish solver convergence, mesh independence, correct physical boundary conditions, or cleanroom performance. GCI remains ineligible while the residual screen fails and quantities of interest are not shown stable.
- Issue [#1296](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/issues/1296) remains open. Verified room/CAD dimensions, diffuser and filter properties, operating conditions, measured supply/extract flow, room pressure, particle concentration/decay where available, and measurement uncertainty are still needed for physical correlation.
- Keep `OF10-UTILITY-foamToVTK` and `OF10-VTK-IMPORT` partial; complete parity counts remain `0/192` native, `0/717` integration, and `0/21` validated cleanroom workflows. This report makes no compatibility percentage claim.

Exact-head checks at `66152ee3e0c9a89d7cac1bbddb85e38a94cb93e8`: CI run [4806](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38694132189), CFD VTK Regression [433](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38694132186), and OpenFOAM Foundation v10 run [58](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38694132081) all succeeded. PR #1311 remains open and unmerged pending scientific validation.
