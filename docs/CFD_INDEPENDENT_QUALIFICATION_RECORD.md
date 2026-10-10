# CFD nine-case independent qualification record

Status: **BLOCKED until actual solver and measured-data evidence are attached**.

This record is a review worksheet, not evidence of execution or certification. It complements [issue #1296](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/issues/1296) and the nine-case execution receipt guide.


## Development and release tracks

**Development: ACTIVE.** Continue implementation, regression testing, documentation and reviewed software changes without waiting for physical validation. A blocked scientific gate does not prohibit ongoing development.

**Software-only release: CONDITIONAL.** A separately scoped software release may be considered only after exact-head required CI, security, packaging, review and reproducibility requirements are met. Label synthetic and unexecuted evidence explicitly; no scientific or cleanroom performance claims are permitted.

**Scientific qualification: BLOCKED.** Real nine-case OpenFOAM runs, numerical convergence and independent measurement correlation remain outstanding. Do not change this status merely to accelerate development.

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

## 6. Deterministic execution and review sequence

Execute these commands only on a machine with a separately verified OpenFOAM Foundation v10 installation and enough CPU, disk and memory. Preserve the original generated family; never rerun into a directory with prior receipts.

```bash
python -m pytest -q tests/test_cfd_grid_runner.py tests/test_cfd_grid_receipt.py tests/test_cfd_pipeline.py
cleanroomx-cfd-pipeline grid-generate examples/cfd_grid_family.example.json ./cfd_mesh_family
cleanroomx-cfd-pipeline grid-run ./cfd_mesh_family --timeout-seconds 3600
cleanroomx-cfd-pipeline grid-verify ./cfd_mesh_family
```

Record the full stdout/stderr, actual exit status, installed package version and Git SHA for each invocation. A green `grid-verify` means only recorded-byte integrity, never physical or numerical validation. Export VTK separately and run `grid-audit` only with a reviewed specification; do not assume that a successful `grid-run` generated VTK.

## 7. Threat model and failure-injection checklist

| Failure mode | Required negative test | Expected disposition |
| --- | --- | --- |
| Replaced source dictionary | Modify one manifest-bound file after generation | Reject before solver launch |
| Replayed output | Substitute another grid's solver/VTK evidence | Ineligible or blocked |
| Symlink substitution | Link manifest, case root, source file or stage log | Reject or report integrity failure |
| Interrupted execution | Terminate between stages, preserve partial receipt | Incomplete, never PASS |
| Nonzero solver exit | Fail one stage without suppressing other cases | Failed case and overall incomplete |
| Truncated log | Change a recorded log after execution | Digest mismatch |
| Forged receipt | Claim physical validation or engineering PASS | Integrity failure |
| Incorrect OpenFOAM | Supply a non-v10 `foamVersion` | Reject before solver launch |
| Invalid mesh ratios | Use equal or non-refining grid spacings | Indeterminate GCI |
| Missing measurements | Supply no independent cleanroom observations | Physical validation unavailable |

These are acceptance-test requirements, not claims that this document executed the tests. An attacker able to rewrite both receipt and digests can defeat local hash matching; use an independently controlled evidence store.

## 8. Quantitative validation worksheet

For every quantity of interest, record the measured value `m`, prediction `p`, consistent units, signed error `p-m`, absolute error `abs(p-m)`, and uncertainty estimates `u_m` and `u_p`. If uncertainty independence is defensible, combined standard uncertainty may be evaluated as `sqrt(u_m^2 + u_p^2)`; otherwise document covariance and use an appropriate correlated uncertainty model. Do not automatically interpret overlap as model validation.

Capture at least: air supply and extract balance, differential pressure, air changes per hour, and any available spatial velocity, tracer decay, or particle measurements. Define sampling locations, calibration records, operational state, uncertainty coverage and acceptance criteria *before* comparing predictions. Keep calibration and independent validation datasets separate.

## 9. Release decision logic

A successful software CI run qualifies only the tested code revision. A complete nine-case run with intact receipts qualifies only the execution evidence for review. A numerically eligible GCI qualifies only the stated discretization-error screen. A physical validation verdict requires traceable independent measurements, documented uncertainties, relevant physics and competent sign-off. No lower gate can substitute for a higher one.

**Default disposition: HOLD / BLOCKED.** No certification, ISO cleanliness class, or fabrication/operational acceptance is implied by this worksheet.
