# CleanroomX Architecture

## Release scope

CleanroomX v0.101.1 (Release 2 final spatial patch) is a Python 3.11+ engineering screening, simulation, verification, uncertainty/provenance, HVAC, fan/network, qualification, and reporting platform. The desktop application is an operator shell over the same backend modules used by the command-line tools. Release 2 consolidates durable project lifecycle, verified persistence/recovery/history, bounded undo-redo, plugin execution, immutable analysis evidence, dependency freshness, portable bundles/reports, deterministic project batch automation, strict engineering JSON ingestion, and final precision/numerical-integrity hardening without duplicating or changing validated solver equations in the GUI.

## Layers

1. **Engineering backends** — calculation, solver, uncertainty, qualification, HVAC, fan/network, dossier, consistency, and report modules under `src/cleanroomx/`. Duct-path, fixed-demand branch-flow, room thermal/air-balance, and supply-fan composition retains full-precision calculation state until the presentation boundary; rounded report fields are not reused for engineering decisions.
2. **Application service registry** — `src/cleanroomx/application.py` defines the desktop workflow catalog and validates unique workflow keys, parser/runner contracts for ordinary workflows, custom `consistency`/`dossier` adapters, and callable parser/runner/reporter targets.
3. **Project persistence** — `src/cleanroomx/project.py` implements the `cleanroomx.project` schema, strict JSON validation, supported legacy migration, duplicate-id and active-analysis checks, lossless preservation of additive fields this build does not interpret, and atomic temporary-file replacement on save.
4. **Recovery persistence** — `src/cleanroomx/autosave.py` owns separate versioned recovery artifacts, source-file fingerprints, bounded rotation, asynchronous write/coalescing, validated restore/discard operations, and recovery scanning. It never writes the explicit project path.
5. **Recovery UI** — `src/cleanroomx/recovery_ui.py` provides startup recovery discovery, evidence inspection, explicit discard, and restore selection without owning project-save semantics.
6. **Desktop UI** — `src/cleanroomx/gui.py` provides project lifecycle, JSON editing, validation, non-blocking execution, per-analysis result ownership, diagnostics, reporting, export, plotting, dirty-state tracking, unsaved-change protection, recovery-autosave status, protected recovery restoration, and active-run mutation guards.
7. **CLI entry points** — `pyproject.toml` exposes CleanroomX commands for verification, HVAC, recovery, uncertainty, qualification, networks, fan studies, dossier/consistency, project batch automation, and the desktop GUI. Every file-producing `--output` path reuses the same fsync-backed, same-directory atomic replacement primitive as desktop exports, so a failed staging write or replacement does not truncate the previously valid report.
8. **Project automation** — `src/cleanroomx/project_batch.py` loads one stable project revision, schedules selected analyses deterministically in persisted project order, delegates execution to the shared application service, preserves per-run provenance, and stops scheduling if the source project changes during the batch.
9. **Verification/provenance** — solver-specific modules retain compatibility, replay, integrity, residual, convergence, coverage, and deterministic reporting evidence. CI preserves explicit v0.91-v0.95 compatibility gates before the complete suite.

## Desktop data flow

Headless project automation uses the same application boundary rather than a second execution stack. `run_project_file()` binds execution to the exact loaded project revision, deep-copies selected analysis inputs, runs them sequentially in persisted project order, and rechecks the source revision before and after every attempt. User-controlled Markdown summary fields reuse the shared Markdown escaping boundary. Engineering PASS/FAIL-style states remain workflow results rather than process-exit semantics.

A project file is loaded through the project persistence boundary and migrated only when it matches a supported legacy shape. Migration-aware loading carries explicit source/target provenance while preserving the historical loader APIs. The desktop keeps migrated legacy files as protected path context and requires the first schema-v1 save to use a different destination, so a one-way migration cannot silently destroy the original source. The selected analysis kind maps to a fixed application-registry entry. Ordinary workflows pass through declared parser and runner functions; consistency and dossier use explicit custom application adapters. Results are normalized to strict JSON and rendered through the backend reporter when available. Foundational room/project verification reports expose a four-state aggregate outcome (`pass`, `fail`, `pass_with_unchecked`, `not_checked`) plus an explicit `complete` flag. The historical `passed` boolean remains a backward-compatible no-failure predicate, so application status rendering distinguishes unresolved evidence from a complete pass without changing legacy CLI exit codes.

Result ownership remains tied to the analysis id, and each cached result is bound to the canonical SHA-256 of the exact submitted analysis input already recorded in execution provenance. Cache restore, worker completion, and result/report export fail closed when the current analysis kind or input hash no longer matches that provenance, so missed mutation notifications cannot silently expose stale engineering evidence. Project saves serialize schema version 1, validate the resulting document, preserve opaque additive fields from the top level, project block, and analysis records, and use an atomic replacement. Known CleanroomX fields remain authoritative if a programmatic extension map attempts to reuse a reserved key.

File-backed application workflows (`consistency` and `dossier`) treat referenced engineering files as revision-bound run inputs. The application captures a stable SHA-256/size/mtime fingerprint before execution and again after report construction. A fingerprint is accepted only when the same file identity, size, and modification timestamp remain stable across the hashing read. If any dependency changes, disappears, or cannot be fingerprinted consistently, `run_analysis()` raises `ExternalDependencyChangedError` and discards the computed run instead of publishing potentially mixed-revision engineering evidence.

Recovery autosave is deliberately outside the project schema. The UI captures a model snapshot plus raw draft state on the Tk thread and submits it to a single background writer. Recovery artifacts are atomically written in a user-specific recovery directory, retain source-project fingerprint evidence, and are bounded by project identity. Explicit saves remain authoritative; recovery artifacts are never substituted for or written over the project file.

Startup restoration keeps save ownership equally explicit. A recovery is parsed through the ordinary project validator, then loaded into the application with no explicit save path and a forced dirty baseline. The original source path, when present, is held separately only for relative-reference context. Therefore Ctrl+S routes through Save As, and a newer or changed source file cannot be overwritten by recovery startup logic.

## Engineering boundary

CleanroomX produces screening and numerical/provenance evidence. It does not by itself establish ISO cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, physical/statistical uncertainty, or regulatory compliance. Applicable requirements and acceptance criteria remain external project inputs.

## Release 2 consolidated architecture

Release 2 keeps validated engineering backends behind a single application boundary while consolidating previously parallel state-management and evidence paths.

- **Persistence authority:** `cleanroomx.persistence` owns durable verified atomic writes and directory durability. Project saves, revision artifacts, exports, recovery artifacts, and bundle publication reuse that boundary instead of implementing independent replace/fsync logic.
- **Project state authority:** `ProjectDocument` owns detached mutable JSON state. `cleanroomx.project_history` provides the bounded application-wide edit transaction stream used by project, analysis, and spatial edits.
- **Saved revision authority:** `cleanroomx.project_revisions` preserves validated prior project bytes and guards overwrites against external file changes. Migration-aware loads bind provenance to the exact stable source revision that was parsed.
- **Recovery authority:** `cleanroomx.autosave` writes session-isolated recovery artifacts with versioned SHA-256 integrity evidence. Legacy v1 artifacts remain readable as explicitly unverified evidence.
- **Execution evidence authority:** `cleanroomx.application` isolates and single-parses submitted inputs, rejects mutation of the execution snapshot, records exact input and external-dependency provenance, and freezes completed run evidence.
- **Run-history authority:** `cleanroomx.run_history` persists a bounded integrity-checked audit ledger without making audit evidence part of undoable design state.
- **Extension and handoff boundaries:** `cleanroomx.plugins` defines analysis plugin API v1; `cleanroomx.project_bundle` owns verified portable project handoff; `cleanroomx.engineering_report` owns verified self-contained HTML engineering reports.

These boundaries do not intentionally change numerical solver equations, tolerances, or acceptance semantics.
