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
digests and source containment. It rejects a manifest whose declared coarse,
medium and fine total cell counts fail to increase strictly, or whose same-level
counts disagree between the three ventilation configurations. These are checks
on the *declared metadata*, not independent validation of the actual OpenFOAM
mesh topology or boundary conditions. The preflight and read-only verifier also
parse each CleanroomX-generated ASCII `system/blockMeshDict` source using a
bounded, restricted grammar: a single vertex list, finite unique vertex
coordinates, exactly the declared number of unique `hex` blocks, distinct
in-range vertex references, the generator's unit subdivisions/grading,
and (also in default, non-capturing preflight) exact exterior face
membership for the generated inlet/outlet/walls boundary patches. The
source screen refuses a missing, duplicated, internal or noncanonical
boundary face even when the local manifest and source digest are
self-rehashed. Full coordinates and patch signatures are only returned
to independent mesh audit callers using `capture_vertices=True`.
The check is repeated against the source digest after parsing. It rejects a
forged self-rehashed dictionary declaring fewer/more blocks than the manifest,
but does **not** parse general OpenFOAM dictionaries, independently verify
geometrical/topological quality, prove actual generated polyMesh cell counts,
or guarantee freedom from filesystem races. It also requires genuinely fresh case directories: only the eight
manifest-bound input files in `0/`, `constant/`, and `system/` are
permitted. For OpenFOAM **Foundation v10**, the case includes
`constant/physicalProperties` (`viscosityModel constant` with `nu`) and
`constant/momentumTransport` (`simulationType laminar`), rather than the
pre-v10 dictionary names. This compatibility change is validated against
published v10 documentation, but still requires a real OpenFOAM v10 smoke run. Hard-linked manifests and generated inputs are rejected even when their contents
match the expected SHA-256: an extra filesystem name could permit untracked
writes from outside the family. The post-run verifier likewise rejects
hard-linked execution receipts and stage logs. Both the runner and independent
verifier now bind streamed file SHA-256 calculations to stable file-descriptor
and path metadata before and after hashing, failing closed on ordinary
concurrent writes or pathname replacement. These checks cannot guarantee
freedom from filesystem races or malicious restore-with-metadata attacks. This is a conservative local
custody screen, **not** proof of provenance or protection against an adversary
who can rewrite both evidence and hashes. Filesystems lacking meaningful
hard-link counts require separate custody controls.

Pre-existing `constant/polyMesh`, result time directories,
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
The runner now also rejects unmanifested files introduced into the immutable
`system/`, `0/`, and `constant/` input directories during a solver
stage, even when all 72 listed source-file digests are unchanged.
The standard `constant/polyMesh/` directory generated by `blockMesh`
is explicitly allowed. The runner checks that this directory and its
nested directories are real (not symlinks), and rejects symlinked, hard-linked,
or non-regular nested mesh files. The check repeats after each stage and in
read-only `grid-verify`, including for an alias introduced after execution.
An unsafe output tree records `source_drift` and halts later cases; these
guards prevent ordinary off-tree aliases, not adversarial race conditions.
For the new **v2** execution receipt, the runner captures a deterministic,
relative-path-to-SHA-256 mapping of the regular files immediately after each
case's `blockMesh` stage (up to 4,096 files and 1 GiB of evidence bytes per
case). It rechecks these immutable mesh bytes immediately before and after
`checkMesh` and `simpleFoam`; any changes are rejected as source drift or
a pre-stage execution blocker, never silently adopted as a new baseline.
The read-only verifier recomputes the original hashes and rejects added, removed,
or edited mesh files even if they remain ordinary nonlinked files. For each
ventilation configuration, it also flags *identical nonempty complete mesh
snapshots* across coarse/medium/fine levels, even if their recorded digests
match. Separate configurations may legitimately share geometric mesh bytes,
so this replay screen is intentionally configuration-local. The mapping
also covers nested directories; unsafe paths and aliases fail closed.
The mapping may be empty if no mesh was produced, which is not a mesh-quality
or mesh-generation acceptance verdict. v1 receipts lack this field and
are rejected rather than silently treated as equivalent to v2 evidence.
A successful hash comparison still cannot prove that recorded outputs came
from an independent OpenFOAM process, or that numerical/physical CFD is valid.
This is scoped to these source directories; other solver-generated output
and time directories require separate scientific review.

The same manifest and source-input checks also run **after** each solver
stage. If the solver itself changes the source bundle, the runner records the
real process return code plus a `source_drift` stage result, marks that case
`execution_failed`, and halts the remaining family without claiming an
execution success. A post-run `grid-verify` considers any recorded
`source_drift` to be failed evidence integrity, even if source bytes are later
restored. This limits but cannot eliminate time-of-check/time-of-use races,
compromised binaries or hostile concurrent filesystem modification.

Each case records stage command, process return code, raw log relative path
and SHA-256, plus a frozen post-`blockMesh` snapshot of generated polyMesh digests.
Receipts are updated atomically after individual stages; cases
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
SHA-256, nine case records, each stage-log path/digest, the final generated
polyMesh file digest mapping, complete-mesh replay within a configuration,
process exit consistency, and deterministic case ordering. A `running` or `not_run` case cannot be
followed by a later started case. The manifest preflight validates its v1
status, specification digest shape, nine configuration metadata structures,
positive mesh quantities, and explicitly non-certifying model limitations;
fabricated certification fields are rejected. The verifier also checks
the retained empty `.grid_run_reserved` directory. Missing, linked, replaced,
or nonempty reservation markers fail the local evidence-integrity screen.
A stage log present on disk but absent from its case's recorded stage list
(for example, after an abrupt interruption between log creation and the next
receipt write) also fails verification as `unreceipted_stage_log`. Preserve
both files for investigation; never delete a log to force a passing verdict.
The verifier also rejects an uncommitted
`.grid_run_evidence.json.tmp` staging file/directory/symlink and any
unrecognized v2 receipt keys or rewritten warning text. These checks flag
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


## Immediate checkMesh solver-launch guard (2026-10-10)

The opt-in `grid-run` now checks the bounded local `checkMesh.log` verdict
**before** launching `simpleFoam`. An explicit `Mesh OK.` followed by
a terminal `End` is required; any `Failed N mesh checks.`, fatal/error
diagnostic, missing verdict, ambiguity, or trailing output blocks that case,
even when `checkMesh` exits with code zero. The runner records the
original return code and SHA-256 log hash with `mesh_check_rejected`,
skips dependent `simpleFoam`, and continues other independent cases.
The immediate gate also requires one printed `cells: N` statistic matching
the generated case manifest's declared cell total. A clean `Mesh OK.` for
the wrong number of cells, duplicate cell statistics or absent cell count
cannot launch `simpleFoam`. The independent verifier binds that comparison
to re-hashed original manifest bytes, including when receipt/log digests
were locally rewritten. This is declared-count integrity, not a
polyMesh topology or independent physical mesh verification.

The offline receipt verifier also checks that a recorded
`mesh_check_rejected` is not contradictory with a clean log and that a
completed `checkMesh` stage contains a clean verdict.

This is a text-integrity safety gate, **not** a mesh-geometry screen,
full OpenFOAM quality certification, solver convergence or physical cleanroom
qualification. Independent mesh/statistic checks remain in
`grid-mesh-audit`; no real OpenFOAM v10 runs or physical measurements
were performed here. Scientific release stays HOLD/BLOCKED.

## Independent checkMesh log-to-mesh consistency gate (2026-10-10)

The read-only `grid-mesh-audit` now also screens each case's recorded
`checkMesh.log` after parsing its actual ASCII `polyMesh`. For all nine cases
it requires one exact standalone `Mesh OK.` verdict, one terminal `End`,
no reported `Failed N mesh checks.` or fatal/error diagnostics, and exactly
one printed value for each of `points`, `faces`, `internal faces` and
`cells`. Those values must equal the counts independently reconstructed
from the corresponding `polyMesh` files. The log must be ordinary,
unlinked, UTF-8 text within a 16 MiB bound and must remain hash-stable
while screened. An external `checkMesh` exit code of zero is not treated
as a substitute for its text verdict: OpenFOAM can print a failure count
even when the utility exits successfully.

The format screen supports the narrow single-time, Foundation-style
`checkMesh` output expected from CleanroomX's controlled serial workflow.
Other formats, multiple mesh-time analyses or missing count lines are
reported as **unverified**, not silently accepted. Matching locally
recorded log content still does not authenticate the tool, prove that
OpenFOAM ran, establish mesh quality against independent thresholds,
or establish convergence/physical performance. All test logs are
**synthetic fixtures**. Scientific review remains **BLOCKED**.

See the OpenFOAM Foundation `checkMesh` source for the distinct
`Mesh OK.` and `Failed N mesh checks.` summary branches.

## Independent ASCII polyMesh structural screening (2026-10-10)

After preserving all nine **real** OpenFOAM mesh outputs, run:

```bash
cleanroomx-cfd-pipeline grid-mesh-audit ./cfd_mesh_family
```

This **read-only** command checks the existing execution receipt with
`grid-verify` and screens each configuration/grid's actual generated
`constant/polyMesh/points`, `faces`, `owner`, `neighbour` and
`boundary` ASCII files. Unlike the input-only `blockMeshDict` screen,
it compares **actual face and cell references** against the declared mesh
cell count. It checks:

- Properly bounded ASCII FoamFile and counted lists; reject binary/compressed,
  missing, symlinked or otherwise unsupported mesh files.
- Finite unique point coordinates, quadrilateral face vertices with valid
  indices, distinct faces, and consistent owner/neighbour lists.
- Exactly six faces per expected generated hexahedral cell and per-cell edge
  multiplicity of two, an elementary **topological** closure check.
- A single connected fluid-cell region (using only internal owner/neighbour
  face adjacencies, not merely shared vertex positions) and the expected
  `wall` / `patch` OpenFOAM boundary declarations.
- No gaps/overlaps in the three inlet/outlet/walls boundary patch ranges,
  and inlet/outlet face counts matching the manifest. For the generated layouts,
  it also checks that supply faces are on the ceiling and exhaust faces lie on
  side x-walls (configurations 1/2) or the floor (configuration 3); this
  rejects correctly counted but incorrectly assigned boundary locations.
- Exact source-to-output boundary patch membership for `inlet`, `outlet`
  and `walls`. The restricted generated dictionary parser verifies each
  patch face corresponds to one external block face; the solver mesh
  audit then binds every face to its original patch using canonical
  vertex identities. It detects inlet/wall face swaps on the same
  ceiling, even when patch counts, plane locations, full vertex lists and
  hexahedral cell membership are unchanged.
- One-to-one hexahedral cell membership comparison: once source and output
  vertex identities are matched, compare the set of eight corner vertices
  for every generated hex block against each reconstructed `polyMesh`
  cell, independent of face/point/cell ordering. This rejects changes
  in cell membership even if all coordinates, outer bounds, counts and
  individually valid cell geometry still match.
- Signed cell volumes are accumulated from the owner-oriented faces (reversed
  for each neighbour) using a cell-local reference point. Nonfinite or
  nonpositive volumes fail the structural screen; the report records the
  minimum and maximum volume in m³. Positivity is only an orientation and
  degeneracy check; no CFD mesh-quality threshold is inferred.
- Full source-to-output vertex-set consistency: the audited mesh must contain
  each generated blockMesh vertex once, independent of OpenFOAM's point order.
  Matching uses bounded three-axis coordinate tolerances (2e-6 of each room
  span) and detects displaced interior vertices even when the room extents
  and hexahedral topology still pass. This is an input/output consistency
  check, not proof of numerical or physical accuracy.
- A non-rewritten unit scale (`convertToMeters 1`) in the generated
  `blockMeshDict`, and a coordinate-bound comparison against the actual
  post-solver ASCII `polyMesh/points` extents. An otherwise connected,
  well-oriented but rescaled or translated room fails this source-bound
  comparison. The 2e-6 per-axis span tolerance covers ASCII roundoff;
  it is a serialization tolerance, not a scientific or regulatory target.
- Stable local mesh-file digests before/after inspection and a complete,
  integrity-consistent previous execution receipt. Unsigned local hashes are
  not independent source authentication.
- Mesh output traversal is capped at 8,192 total entries and 64 directory
  levels per case, in addition to 4,096 regular files and 1 GiB of file bytes.
  Unexpected input-directory entries fail as soon as the expected set is
  exceeded; links and nonregular entries also fail closed.

A fully screened nine-case family is labeled
`mesh_structure_screened_requires_scientific_review` (CLI exit 0).
Missing files, incomplete execution receipts, unsupported OpenFOAM formats or
mismatched mesh topology are **not** accepted (exit 3). Unit tests construct
**synthetic** ASCII meshes: they are parser regressions, not actual OpenFOAM
runs, physical qualification or evidence of CFD correctness.

**Limits:** The bounded parser intentionally accepts only the predictable,
small, ASCII hexahedral meshes generated by the CleanroomX workflow.
It is not a full OpenFOAM parser or solver. The auditor additionally
screens individual faces for zero area, nonplanarity and owner/neighbour
normal direction (with a bounded numerical tolerance), and requires eight
identified vertices per hexahedral cell, and positive signed cell volumes.
These elementary geometric sanity checks cannot establish CFD-quality volume
magnitudes, acceptable nonorthogonality, skewness, wall metrics, mass
conservation, numerical convergence or cleanroom performance.
Inspect real `checkMesh` logs, residuals, VTK fields, independent grid
studies and measured data before any scientific or release decision.
Scientific/physical review remains **BLOCKED**.

Source: [OpenFOAM mesh files](https://doc.cfd.direct/openfoam/user-guide-v13/mesh-files)
and [OpenFOAM mesh validity constraints](https://www.openfoam.com/documentation/user-guide/4-mesh-generation-and-conversion/4.1-mesh-description).

## CI-backed OpenFOAM v10 smoke run

`.github/workflows/cfd-openfoam-grid.yml` runs for relevant pull request changes
and can also be started with `workflow_dispatch`. On Ubuntu 22.04 it installs
OpenFOAM Foundation v10, generates the example family below, executes all nine
cases through `blockMesh`, `checkMesh`, and `simpleFoam`, then runs
`grid-verify` and `grid-mesh-audit`. A failed `grid-run` still triggers both
read-only evidence screens, with each actual exit code recorded; any nonzero
result fails the workflow. The workflow retries transient download failures
while installing the official OpenFOAM Foundation v10 package, which depends
on a large ParaView download. This does not change the solver version.

The workflow packs the generated family, OpenFOAM version and command exit codes
in `openfoam-v10-grid-evidence.tar.gz` (retained for 14 days). The TAR format
is deliberate: GitHub directory artifacts can omit hidden entries and empty
directories, but local `grid-verify` requires the **empty**
`.grid_run_reserved` marker. The archive is created even when the CFD commands
fail, provided any execution evidence exists. After downloading, inspect the
archive's contents and extract it in a trusted, fresh directory (do not merge
with an earlier run):

```bash
tar -tzf openfoam-v10-grid-evidence.tar.gz | head
tar -xzf openfoam-v10-grid-evidence.tar.gz -C ./fresh-evidence
cleanroomx-cfd-pipeline grid-verify ./fresh-evidence/cleanroomx-cfd-grid-family
```

Create `fresh-evidence` before extraction. Keep the GitHub artifact digest,
exact head commit, CI run URL and an independent copy of the TAR for longer
review. The artifact is short-lived and is **not** authenticated provenance,
proof of physical validation, or evidence of convergence merely because its
integrity hashes match. A failed or incomplete run stays explicitly BLOCKED.

The example specification is explicitly synthetic. A green workflow therefore
demonstrates software integration with a real OpenFOAM v10 installation and
local evidence/mesh screening for that synthetic case family. It does not
establish convergence, independent mesh quality, real-room performance,
physical correlation, or release readiness. Keep scientific review **BLOCKED**
until project-specific inputs, numerical review, independent measurements, and
all release evidence are available.
