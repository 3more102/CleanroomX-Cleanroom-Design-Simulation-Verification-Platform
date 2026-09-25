# CleanroomX Architecture

## Release scope

CleanroomX v0.100.0 is a Python 3.11+ engineering screening, simulation, verification, uncertainty/provenance, HVAC, fan/network, qualification, and reporting platform. The desktop application is an operator shell over the same backend modules used by the command-line tools. v0.100 adds application execution provenance, portable external-file path handling, atomic persistence/exports, and backend-evidence fan/system plotting without duplicating validated solver equations in the GUI.

## Layers

1. **Engineering backends** — calculation, solver, uncertainty, qualification, HVAC, fan/network, dossier, consistency, and report modules under `src/cleanroomx/`.
2. **Application service registry** — `src/cleanroomx/application.py` defines the desktop workflow catalog and validates unique workflow keys, parser/runner contracts for ordinary workflows, custom `consistency`/`dossier` adapters, and callable parser/runner/reporter targets.
3. **Project persistence** — `src/cleanroomx/project.py` implements the `cleanroomx.project` schema, strict JSON validation, supported legacy migration, duplicate-id and active-analysis checks, and atomic temporary-file replacement on save.
4. **Analysis run history** — `src/cleanroomx/run_history.py` owns bounded, versioned run-history metadata, exact submitted-input snapshots, entry/history SHA-256 validation, safe restoration of exact-input matches, and fail-closed export validation.
5. **Recovery persistence** — `src/cleanroomx/autosave.py` owns separate versioned recovery artifacts, source-file fingerprints, bounded rotation, asynchronous write/coalescing, validated restore/discard operations, and recovery scanning. It never writes the explicit project path.
6. **Recovery UI** — `src/cleanroomx/recovery_ui.py` provides startup recovery discovery, evidence inspection, explicit discard, and restore selection without owning project-save semantics.
7. **Desktop UI** — `src/cleanroomx/gui.py` provides project lifecycle, JSON editing, validation, non-blocking execution, per-analysis result ownership, persisted-history hydration, diagnostics, reporting, export, plotting, dirty-state tracking, unsaved-change protection, recovery-autosave status, protected recovery restoration, and active-run mutation guards.
8. **CLI entry points** — `pyproject.toml` exposes CleanroomX commands for verification, HVAC, recovery, uncertainty, qualification, networks, fan studies, dossier/consistency, and the desktop GUI. Every file-producing `--output` path reuses the same fsync-backed, same-directory atomic replacement primitive as desktop exports, so a failed staging write or replacement does not truncate the previously valid report.
9. **Verification/provenance** — solver-specific modules retain compatibility, replay, integrity, residual, convergence, coverage, and deterministic reporting evidence. CI preserves explicit v0.91-v0.95 compatibility gates before the complete suite.

## Desktop data flow

A project file is loaded through `load_project_document()` and migrated only when it matches a supported legacy shape. The selected analysis kind maps to a fixed application-registry entry. Ordinary workflows pass through declared parser and runner functions; consistency and dossier use explicit custom application adapters. Results are normalized to strict JSON and rendered through the backend reporter when available.

Result ownership remains tied to the analysis id, and each cached result is bound to the canonical SHA-256 of the exact submitted analysis input already recorded in execution provenance. Cache restore, worker completion, and result/report export fail closed when the current analysis kind or input hash no longer matches that provenance, so missed mutation notifications cannot silently expose stale engineering evidence.

Accepted desktop runs are additionally appended to a bounded `cleanroomx.analysis_run_history` metadata block. Each record preserves the exact submitted input snapshot plus the complete `AnalysisRun` payload and its existing execution provenance, then protects the record and ordered history container with canonical SHA-256 digests. Project/recovery open performs one validation/hydration pass and restores only the latest record that still matches the current analysis kind/input; stale and removed-analysis records remain audit evidence but are not exposed as current results. Any malformed, unsupported, oversized, or integrity-mismatched history fails closed and is preserved rather than rewritten. The embedded history is capped at 25 records, 5 per analysis, and 8 MiB. Dirty-state comparison excludes the potentially large history payload and tracks controlled history mutation with an in-memory generation counter, avoiding history-size-dependent work on every editor keystroke.

Project saves continue to serialize schema version 1, validate the resulting document, and use an atomic replacement. Run history therefore uses the existing metadata compatibility channel rather than introducing a file-format migration. Recovery snapshots include the metadata block, so an accepted run that has not yet been explicitly saved remains recoverable through the existing autosave path.

File-backed application workflows (`consistency` and `dossier`) treat referenced engineering files as revision-bound run inputs. The application captures a stable SHA-256/size/mtime fingerprint before execution and again after report construction. A fingerprint is accepted only when the same file identity, size, and modification timestamp remain stable across the hashing read. If any dependency changes, disappears, or cannot be fingerprinted consistently, `run_analysis()` raises `ExternalDependencyChangedError` and discards the computed run instead of publishing potentially mixed-revision engineering evidence.

Recovery autosave is deliberately outside the project schema. The UI captures a model snapshot plus raw draft state on the Tk thread and submits it to a single background writer. Recovery artifacts are atomically written in a user-specific recovery directory, retain source-project fingerprint evidence, and are bounded by project identity. Explicit saves remain authoritative; recovery artifacts are never substituted for or written over the project file.

Startup restoration keeps save ownership equally explicit. A recovery is parsed through the ordinary project validator, then loaded into the application with no explicit save path and a forced dirty baseline. The original source path, when present, is held separately only for relative-reference context. Therefore Ctrl+S routes through Save As, and a newer or changed source file cannot be overwritten by recovery startup logic.

## Engineering boundary

CleanroomX produces screening and numerical/provenance evidence. It does not by itself establish ISO cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, physical/statistical uncertainty, or regulatory compliance. Applicable requirements and acceptance criteria remain external project inputs.
