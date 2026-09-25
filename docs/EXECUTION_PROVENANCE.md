# Execution implementation provenance

CleanroomX application runs bind engineering evidence to both the submitted input and the exact installed Python-source revision used by the application layer.

## Recorded evidence

Each completed `AnalysisRun` adds an `implementation` block inside `diagnostics.application_execution_provenance`. It records:

- the `cleanroomx.execution-implementation` evidence schema and version (distinct from the compact `cleanroomx.implementation-revision` readiness snapshot);
- the source-tree canonicalization contract;
- SHA-256 of the CleanroomX Python source tree before and after the run;
- source-file counts before and after the run;
- whether the runtime and source tree remained stable;
- deterministic changed-file paths when a difference is detected;
- Python implementation/version/cache tag/compiler and OS system/release/machine identity;
- the configured validation, execution, and reporting entry points for the selected workflow.

The aggregate source identity includes every `*.py` file under the installed `cleanroomx` package. Each file is required to resolve to a regular file, is read through a stable descriptor/stat check, and the Python-source file set is re-enumerated before the fingerprint is accepted. Line endings are normalized to LF, and only each package-relative POSIX path, canonical byte count, and SHA-256 contribute to the aggregate. Absolute installation paths are never included.

## Failure behavior

The implementation revision is captured before input validation and again after result normalization, report generation, diagnostics construction, plotting, and external-dependency recapture. If any CleanroomX Python source file was added, removed, or changed across that window, `run_analysis()` raises `ImplementationChangedError` and does not return an `AnalysisRun`. If a stable source fingerprint cannot be established, `ImplementationProvenanceError` aborts execution rather than fabricating provenance.

This behavior is intentionally fail-closed for traceability. It does not modify solver equations, tolerances, engineering criteria, project schema version 1, or backend result semantics.

## Installation/readiness identity

`cleanroomx-gui --check` exposes a compact current implementation revision with source-tree SHA-256, file count, canonicalization contract, and runtime identity. Per-file hashes are retained only transiently while comparing revisions; they are not emitted in every run bundle, keeping diagnostics bounded while still localizing changed files if an execution becomes unstable.

## Security and reproducibility boundary

The digest is deterministic integrity/reproducibility evidence, not a digital signature, publisher attestation, or proof of engineering correctness. It identifies the on-disk CleanroomX Python source tree and recorded runtime. It does not attest arbitrary third-party/native libraries, operating-system correctness, hardware behavior, or in-memory monkeypatching performed after Python imported a module. Controlled deployments should still retain the wheel/source artifact, release metadata, and normal organizational approval records alongside exported engineering evidence.
