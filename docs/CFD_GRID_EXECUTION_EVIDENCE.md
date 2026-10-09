# Nine-case OpenFOAM execution receipts

## Scope

`cleanroomx-cfd-pipeline grid-run` is **explicit opt-in**. It executes the
nine existing generated OpenFOAM case directories, one after another, using
`blockMesh`, `checkMesh`, and `simpleFoam`, and writes machine-readable
`grid_run_evidence.json`. This is an execution and provenance recorder,
**not** a CFD numerical acceptance gate or cleanroom certification.

This is the next reproducible-execution step for
[CFD physical validation issue #1296](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/issues/1296).

## Before execution

- Install and activate **OpenFOAM Foundation v10**, including `foamVersion`,
  `blockMesh`, `checkMesh`, and `simpleFoam` in `PATH`.
- Use a **fresh**, generated nine-case family and explicitly reviewed
  project-specific geometry, flow, and viscosity inputs. The example is
  synthetic and is **not** a real cleanroom.
- Ensure sufficient storage and computational resources for nine solver runs;
  do not run on an untrusted bundle.
- Generation retains the **20,000 hexahedral cells per case** guard. Do not
  interpret this generation cap as an accuracy target or physical acceptance
  threshold.

## Commands

```bash
cleanroomx-cfd-pipeline grid-generate \
  examples/cfd_grid_family.example.json ./cfd_mesh_family

# Executes external programs; may consume significant CPU and disk.
cleanroomx-cfd-pipeline grid-run ./cfd_mesh_family --timeout-seconds 3600
```

The executable first validates that the generation manifest lists exactly nine
cases and all 72 expected generated inputs, and confirms input SHA-256
digests and source containment. It rejects any prior run receipt or stage log
to prevent overwriting evidence, and verifies the `foamVersion` result against
the targeted Foundation v10 version. These are structural and software
provenance checks, not guarantees of scientific fidelity or filesystem race
freedom.

Each case records stage command, process return code, raw log relative path
and SHA-256. Receipts are updated atomically after individual stages; cases
with failed stages are reported as `execution_failed` while remaining cases
are attempted. `status: incomplete` requires investigation and cannot pass
review. When every process exits successfully the report status is
`executed_requires_convergence_review`, **not** `validated`.

The receipt's `engineering_review` remains `BLOCKED` and
`physical_validation` remains `not_performed` **even when all 27 stage
commands exit zero**. Executable paths and the reported version are
provenance hints, not an attestation of the binary distribution or run
environment. Keep raw logs and case output with the receipt.

## What remains mandatory

1. Inspect real `checkMesh` quality outputs, SIMPLE solver residual histories,
   flux/continuity convergence, boundary values and physical realism.
2. Export real computed fields to VTK for the three meshes of each configuration
   and collect distinct solver logs. No VTK export is performed by this runner.
3. Run `cleanroomx-cfd-pipeline grid-audit` separately on each family of
   **real** three-grid fields with explicitly justified project tolerances.
4. Add independent measured cleanroom data and uncertainty-aware comparisons
   for the same operating conditions. Without this, physical validation
   is unavailable.

**Do not call the generated sample a validated cleanroom, or claim that
a successful simulation establishes particle cleanliness or ISO classification.**

## Testing boundary

Automated runner tests mock subprocess exits and logs to verify software
behavior. They **never invoke OpenFOAM**, and their outputs must not be
reported as independent CFD or measured cleanroom evidence.
