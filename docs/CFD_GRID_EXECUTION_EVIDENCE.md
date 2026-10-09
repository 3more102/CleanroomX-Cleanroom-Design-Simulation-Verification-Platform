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
digests and source containment. It also requires genuinely fresh case directories: only the eight
manifest-bound input files in `0/`, `constant/`, and `system/` are
permitted. For OpenFOAM **Foundation v10**, the case includes
`constant/physicalProperties` (`viscosityModel constant` with `nu`) and
`constant/momentumTransport` (`simulationType laminar`), rather than the
pre-v10 dictionary names. This compatibility change is validated against
published v10 documentation, but still requires a real OpenFOAM v10 smoke run. Pre-existing `constant/polyMesh`, result time directories,
`postProcessing`, extra files or symbolic-link substitutions are rejected
*before* any external process starts. Remove stale output only by deliberately
regenerating a clean family in a **new directory**, not by overwriting
historical run evidence. The family manifest, configuration root directories and case roots must also
be real filesystem objects, not symlinks, including those resolving inside the
family with byte-identical content. The post-run verifier independently checks
the manifest and configuration-root substitutions as well as linked case and
source paths. This is a source freshness and filesystem screen,
not an assertion that the solver binary or physical setup is trustworthy.
It rejects any prior run receipt or stage log
to prevent overwriting evidence, and verifies the `foamVersion` result against
the targeted Foundation v10 version. These are structural and software
provenance checks, not guarantees of scientific fidelity or filesystem race
freedom. To reduce stale-source execution risk, the runner additionally
rehashes the original manifest and each case's eight manifest-bound inputs
**immediately before each external stage** (including the first stage after
`foamVersion`). If an input or the manifest changed, it stops without
launching the next process, preserves its existing incomplete receipt and
reservation, and requires a new independently generated family for re-run.
This limits but cannot eliminate time-of-check/time-of-use races, compromised
binaries or hostile concurrent filesystem modification.

Each case records stage command, process return code, raw log relative path
and SHA-256. Receipts are updated atomically after individual stages; cases
with failed stages are reported as `execution_failed` while remaining cases
are attempted. Even if an external stage exits with code 0, an empty log is
marked `empty_output`, its dependent stages are not started, and that case
remains failed. The true process return code is retained; absence of output
is a software evidence gate, not a numerical convergence criterion.
The post-run verifier also requires `empty_output` to correspond to an actually
empty log; a forged status paired with nonempty bytes is rejected. `status: incomplete` requires investigation and cannot pass
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

## Independent post-run integrity screen

Run the read-only verifier on the preserved nine-case family after execution or transfer:

```bash
cleanroomx-cfd-pipeline grid-verify ./cfd_mesh_family
```

The `grid-verify` command checks the 72 generated input hashes, recorded manifest
SHA-256, nine case records, each stage-log path/digest, process exit consistency,
and deterministic case ordering. A `running` or `not_run` case cannot be
followed by a later started case. The manifest preflight validates its v1
status, specification digest shape, nine configuration metadata structures,
positive mesh quantities, and explicitly non-certifying model limitations;
fabricated certification fields are rejected.
and the retained empty `.grid_run_reserved` directory. Missing, linked, replaced,
or nonempty reservation markers fail the local evidence-integrity screen.
A stage log present on disk but absent from its case's recorded stage list
(for example, after an abrupt interruption between log creation and the next
receipt write) also fails verification as `unreceipted_stage_log`. Preserve
both files for investigation; never delete a log to force a passing verdict.
The verifier also rejects an uncommitted
`.grid_run_evidence.json.tmp` staging file/directory/symlink and any
unrecognized v1 receipt keys or rewritten warning text. These checks flag
inconsistent local evidence; they are not cryptographic authenticity.
Missing/modified inputs or logs, symlinked logs, forged validation claims,
byte-empty logs from completed stages, and byte-identical `simpleFoam` logs
reused across any two of the nine cases fail closed, including reuse between
different ventilation configurations. This extra replay screen cannot prove
run independence when logs differ; the verifier does not invoke OpenFOAM.

A complete consistent receipt returns
`execution_logs_integrity_verified_requires_scientific_review` (exit 0).
A consistent incomplete execution returns
`incomplete_execution_logs_integrity_verified` (exit 3).
Tampered or malformed evidence returns `evidence_integrity_failed` (exit 3).
Regardless of integrity, `engineering_review` remains `BLOCKED` and
`physical_validation` remains `not_performed`.

**Trust boundary:** The receipt is unsigned and its SHA-256 hashes can be
consistently rewritten by someone who controls all evidence files. Hash
agreement does not attest executable identity, prove independent solver
runs or validate scientific/physical results. Preserve immutable external
copies and trusted timestamps/signatures where chain-of-custody is required.


## Concurrent execution reservation (2026-10-09)

After validating the OpenFOAM executable version and before launching any stage, `grid-run` atomically creates the directory `.grid_run_reserved` inside the generated family. A second invocation cannot create that directory and is rejected without running a solver. This is a local filesystem coordination safeguard, **not** a distributed lock or an authenticated run identifier. The reservation is deliberately retained after success, failure or interruption; existing stage logs and the receipt remain the authoritative execution evidence. Do **not** delete the reservation to force an implicit restart. Instead archive and independently verify the entire original family, then generate a fresh family in a new directory for a new run attempt. The runner does not yet provide automatic recovery or cryptographically authenticated custody. No physical or numerical approval follows from a reservation or an exit-code-zero receipt.
