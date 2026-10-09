# CFD nine-case independent qualification record

Status: **BLOCKED until actual solver and measured-data evidence are attached**.

This record is a review worksheet, not evidence of execution or certification. It complements [issue #1296](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/issues/1296) and the nine-case execution receipt guide.

## 1. Immutable provenance

Record the Git commit, operating system, OpenFOAM Foundation v10 patch version, executable locations and independently computed binary SHA-256 digests, CPU architecture, timestamp with timezone, and operator. Preserve the generated input manifest, raw source files, run receipt, all 27 stage logs, and solver output in read-only storage. Record a separately stored digest manifest and its custody owner. A digest in the same editable directory is not independent attestation.

## 2. Nine-case execution matrix

Fill one row per actual case; never infer results from synthetic tests.

| Configuration | Grid | blockMesh | checkMesh | simpleFoam | Input SHA-256 verified | Log SHA-256 verified | Mesh quality review | Residual/continuity review | VTK field SHA-256 | Verdict |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | coarse | NOT RUN | NOT RUN | NOT RUN | UNVERIFIED | UNVERIFIED | NOT REVIEWED | NOT REVIEWED | MISSING | BLOCKED |
| 1 | medium | NOT RUN | NOT RUN | NOT RUN | UNVERIFIED | UNVERIFIED | NOT REVIEWED | NOT REVIEWED | MISSING | BLOCKED |
| 1 | fine | NOT RUN | NOT RUN | NOT RUN | UNVERIFIED | UNVERIFIED | NOT REVIEWED | NOT REVIEWED | MISSING | BLOCKED |
| 2 | coarse | NOT RUN | NOT RUN | NOT RUN | UNVERIFIED | UNVERIFIED | NOT REVIEWED | NOT REVIEWED | MISSING | BLOCKED |
| 2 | medium | NOT RUN | NOT RUN | NOT RUN | UNVERIFIED | UNVERIFIED | NOT REVIEWED | NOT REVIEWED | MISSING | BLOCKED |
| 2 | fine | NOT RUN | NOT RUN | NOT RUN | UNVERIFIED | UNVERIFIED | NOT REVIEWED | NOT REVIEWED | MISSING | BLOCKED |
| 3 | coarse | NOT RUN | NOT RUN | NOT RUN | UNVERIFIED | UNVERIFIED | NOT REVIEWED | NOT REVIEWED | MISSING | BLOCKED |
| 3 | medium | NOT RUN | NOT RUN | NOT RUN | UNVERIFIED | UNVERIFIED | NOT REVIEWED | NOT REVIEWED | MISSING | BLOCKED |
| 3 | fine | NOT RUN | NOT RUN | NOT RUN | UNVERIFIED | UNVERIFIED | NOT REVIEWED | NOT REVIEWED | MISSING | BLOCKED |

For each row attach the exact stage exit codes and paths to raw logs. Successful exit is not convergence.

## 3. Numerical review per ventilation configuration

Record physical dimensions and units, boundary-condition provenance, Reynolds-number and turbulence-model applicability, mesh cell counts, nonorthogonality/skewness and checkMesh warnings, solver stopping criteria, final residual histories, flux imbalance and continuity error, and any divergence. For each configuration attach distinct coarse/medium/fine VTK outputs and run the existing `grid-audit` with documented project-specific tolerances. Record the observed convergence order, Richardson extrapolation, GCI and all indeterminate or ineligible verdicts. Never manufacture an acceptance threshold or interpret a small GCI as physical validation.

## 4. Independent measurement comparison

Attach measured supply/extract flows, pressure differentials, ACH and particle/tracer results where available, with sensor calibration, timestamps, measurement locations, uncertainties and operating conditions. Distinguish calibration data from held-out validation measurements. Report prediction-minus-measurement error and combined uncertainty for each comparable quantity. Mark missing measurements as **NOT AVAILABLE**, not PASS.

## 5. Gate and sign-off

- Software CI (Python 3.11/3.12/3.13, Windows, native BIM, CFD VTK and Required CI Gate): **UNVERIFIED FOR EXACT PR HEAD**
- Nine-case real OpenFOAM execution: **NOT PERFORMED**
- Evidence integrity and independent custody: **NOT VERIFIED**
- Three-grid convergence: **NOT VERIFIED**
- Independent physical correlation: **NOT AVAILABLE**
- Scientific/engineering review: **BLOCKED**
- Release/certification: **NOT AUTHORIZED**

Reviewer: _unassigned_. Review date: _not recorded_. External evidence archive: _not provided_.

Do not change these defaults until traceable evidence supports each field.