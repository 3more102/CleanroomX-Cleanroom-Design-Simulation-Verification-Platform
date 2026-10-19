# OpenFOAM Foundation v10 run 67: grid execution evidence

## Run provenance

- GitHub Actions run [38777678904](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38777678904) completed against PR #1311 head `b3d40fbe24ce6bb9fd83c26c0008b85ba3187068`; Actions executed merge commit `7e5e2a8593c692ccda35e1488e520bf598842c65`.
- Solver: OpenFOAM Foundation v10, build `10-c4cf895ad8fa`.
- Evidence archive [11994032855](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/runs/38777678904/artifacts/11994032855), SHA-256 `4e8725c04924f947a60623ba5c36993decba51fe6bf0cf21e4f5b923ffb8411f`.
- The archive contains 304 files, including the 72 input-file digests, 36 command logs, generated meshes, solver outputs, VTK files, execution receipt, and triage JSON.

All nine synthetic cases completed `blockMesh`, `checkMesh`, `simpleFoam`, and
`foamToVTK` with return code 0 (36/36 stages). The boundary-input audit
reconstructed generated faces and outward normals and confirmed that the
prescribed inlet flow matches each synthetic input. It does not validate an
outlet flow, measured room conditions, or physical geometry.

Each `checkMesh` log reports `Mesh OK.` The coarse, medium, and fine meshes
contain 216, 1,728, and 13,824 cells respectively; the three configurations
share those counts and the archived geometric diagnostics. As in
[run 66](OPENFOAM_V10_RUN_38776224839_CHECKMESH_QUALITY.md), no project mesh
quality criteria or verified physical geometry are available.

## Per-case solver and field evidence

Each `simpleFoam` run reached 150 seconds. The configured terminal residual
screen reports `U` and `p` as `NOT_BELOW_TOLERANCE` in every case. The
log-based vector-`U` screen uses the maximum component initial residual and
does not reproduce OpenFOAM's internal `residualControl` calculation. Final
`phi` fluxes were measured, but no project flow-balance acceptance criterion
is set.

| Case | Cells | Residual screen | Flux imbalance | `checkMesh.log` SHA-256 | `simpleFoam.log` SHA-256 | Internal VTK SHA-256 |
|---|---:|---|---:|---|---|---|
| configuration_1/coarse | 216 | U/p not below tolerance | 0.0908043501151% | `3a1e897a7fc7a121d8085e5906699d6b71ffaef60348a4044ec3319eac51005f` | `57e172e373b888b2f7277584e1c01c10be5bb51c88c0bb7591444c0fa4e95dce` | `9891175457c1a3e1a6a8771e5951b351374dc0714dd2c27235557c0d9834fb39` |
| configuration_1/medium | 1,728 | U/p not below tolerance | 0.00534133556299% | `97452cc12a737163dc48e17ffd8c0cd2c98b0dfc63a58c938fbde0c550e0ee27` | `e0cfcaee550bf0350ba7f0715447b90decb8128c6223701841bfdbc5df83250b` | `651942d759d11f0df0782258b024001563f0f675d799711cb23bebc2bd163414` |
| configuration_1/fine | 13,824 | U/p not below tolerance | 0.124262549062% | `e283f8cdb241a55dd974a28046a4c9247b6852c12f75c1c9c762a59c43bacbca` | `2861ba674885c40c5ebf963966c604d58af553a098078c1c05c630c7dacad1ff` | `02faa11ca08560aa6d8074d1804154aace018d5118b57bb815badf2fbf7a84a0` |
| configuration_2/coarse | 216 | U/p not below tolerance | 0.187145329221% | `0befab48db8a97bde2310519969ef4ceaac5bd4c1aa4994908887044128064b4` | `116538e00f993e7cef6ba594db75ab1b143d03e97b79b7e5fc5911177ed0413a` | `81f7bd45d29fad73529dda8a1beb6ad5340481079614e0b36a072c7df139ad8e` |
| configuration_2/medium | 1,728 | U/p not below tolerance | 0.091543919063% | `7d1ef7dce02dbc8b4915eacfc465931eca1dbc25e6e25820637ecaba5289b0f6` | `e54c4859f0af3013129ccee0e72b72694d8536866b882a146cb647d0a12110a4` | `ff65af8c53eaa583af575e2be85c7bca1f3ef1b5b1a948f0147c8fefe10ff027` |
| configuration_2/fine | 13,824 | U/p not below tolerance | 0.0356121650724% | `ea388d8bebb4dcba1e1e3aa7005b5ebf314123279a3da9fe1e33785bd70108dd` | `3e26b7bc00093f10c693ce8007c91495729cc544f867254e991573b252e996b6` | `c150aef692458224ebc4839de7fd44a4346ea740509c5ba853ccf3e3eec43149` |
| configuration_3/coarse | 216 | U/p not below tolerance | 0.170934559897% | `90c0fdd489cd881abd812aa8ed5723c5d40882914894db3637325c8ba34c53ad` | `8846d07cc73606b8f328184c0f5bc2d6f02b4942caf3430fd68df8e228909679` | `c9f4ba72e1d8f5bd7346491d0b0938113e0a644561606c5ce71900c6f9566b9d` |
| configuration_3/medium | 1,728 | U/p not below tolerance | 0.0709769219972% | `c38eccf34a839977c54b7c21143e747194d6985d300388963921ede77cbc9a4c` | `836d0ae9c326d2189436e5b3efcbf73c61d7270755ac5506198cb7d6181a7d1f` | `7e263c12e44f5ff91c5caffb5acdf13cb454495e7f7a779ee21472d91811c273` |
| configuration_3/fine | 13,824 | U/p not below tolerance | 0.0562197545423% | `eb5113821704c9aa43b9ac6747018f239a410f3ea20523f0ca8de1b36d1c5fe2` | `4338153fb619a10c4bbe0b19a2193580d1085468d5d8fc874205b62ba4e67891` | `f8e7db16005cb7b54048709caf794452a2945b2045e366d2f60b9bd313095e41` |

The nine internal VTK datasets passed native-field parity for `U` and `p`:
47,304 cells, 141,912 velocity components, and 47,304 pressure values. The 27
separate inlet/outlet/walls patch datasets also passed parity for 13,608 faces,
40,824 velocity components, and 13,608 pressure values. Their individual
digests and comparison tolerances are in the archived execution evidence.

## Validation status

This is reproducible execution and serialization evidence for generated,
synthetic rectangular cases. Residual screening did not pass in any case, flux
balance has no project acceptance criterion, and no project mesh-quality
criteria or independent cleanroom measurements are available. No GCI result or
physical validation is claimed; issue #1296 and scientific validation remain
open and blocked.
