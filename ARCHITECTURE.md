# CleanroomX Architecture

## Release scope

CleanroomX v0.100.0 is a Python 3.11+ engineering screening, simulation, verification, uncertainty/provenance, HVAC, fan/network, qualification, and reporting platform. The desktop application is an operator shell over the same backend modules used by the command-line tools. v0.100 adds application execution provenance, portable external-file path handling, atomic persistence/exports, and backend-evidence fan/system plotting without duplicating validated solver equations in the GUI.

## Layers

1. **Engineering backends** — calculation, solver, uncertainty, qualification, HVAC, fan/network, dossier, consistency, and report modules under `src/cleanroomx/`.
2. **Application service registry** — `src/cleanroomx/application.py` defines the desktop workflow catalog and validates unique workflow keys, parser/runner contracts for ordinary workflows, custom `consistency`/`dossier` adapters, and callable parser/runner/reporter targets.
3. **Project persistence** — `src/cleanroomx/project.py` implements the `cleanroomx.project` schema, strict JSON validation, supported legacy migration, duplicate-id and active-analysis checks, and atomic temporary-file replacement on save.
4. **Recovery persistence** — `src/cleanroomx/autosave.py` owns separate versioned recovery artifacts, source-file fingerprints, bounded rotation, asynchronous write/coalescing, validated restore/discard operations, and recovery scanning. It never writes the explicit project path.
5. **Recovery UI** — `src/cleanroomx/recovery_ui.py` provides startup recovery discovery, evidence inspection, explicit discard, and restore selection without owning project-save semantics.
6. **Desktop UI** — `src/cleanroomx/gui.py` provides project lifecycle, JSON editing, validation, non-blocking execution, per-analysis result ownership, diagnostics, reporting, export, plotting, dirty-state tracking, unsaved-change protection, recovery-autosave status, protected recovery restoration, and active-run mutation guards.
7. **CLI entry points** — `pyproject.toml` exposes CleanroomX commands for verification, HVAC, recovery, uncertainty, qualification, networks, fan studies, dossier/consistency, and the desktop GUI.
8. **Verification/provenance** — solver-specific modules retain compatibility, replay, integrity, residual, convergence, coverage, and deterministic reporting evidence. CI preserves explicit v0.91-v0.95 compatibility gates before the complete suite.
9. **Portable engineering reporting** — `src/cleanroomx/engineering_report.py` composes one exact completed application run into deterministic self-contained HTML after independently rechecking run/input provenance. It embeds strict machine-readable evidence plus a canonical SHA-256 and never invokes or reimplements engineering solvers.

## Desktop data flow

A project file is loaded through `load_project_document()` and migrated only when it matches a supported legacy shape. The selected analysis kind maps to a fixed application-registry entry. Ordinary workflows pass through declared parser and runner functions; consistency and dossier use explicit custom application adapters. Results are normalized to strict JSON and rendered through the backend reporter when available.

Result ownership remains tied to the analysis id, and each cached result is bound to the canonical SHA-256 of the exact submitted analysis input already recorded in execution provenance. Cache restore, worker completion, and result/report export fail closed when the current analysis kind or input hash no longer matches that provenance, so missed mutation notifications cannot silently expose stale engineering evidence. Project saves serialize schema version 1, validate the resulting document, and use an atomic replacement.

File-backed application workflows (`consistency` and `dossier`) treat referenced engineering files as revision-bound run inputs. The application captures a stable SHA-256/size/mtime fingerprint before execution and again after report construction. A fingerprint is accepted only when the same file identity, size, and modification timestamp remain stable across the hashing read. If any dependency changes, disappears, or cannot be fingerprinted consistently, `run_analysis()` raises `ExternalDependencyChangedError` and discards the computed run instead of publishing potentially mixed-revision engineering evidence.

Recovery autosave is deliberately outside the project schema. The UI captures a model snapshot plus raw draft state on the Tk thread and submits it to a single background writer. Recovery artifacts are atomically written in a user-specific recovery directory, retain source-project fingerprint evidence, and are bounded by project identity. Explicit saves remain authoritative; recovery artifacts are never substituted for or written over the project file.

Startup restoration keeps save ownership equally explicit. A recovery is parsed through the ordinary project validator, then loaded into the application with no explicit save path and a forced dirty baseline. The original source path, when present, is held separately only for relative-reference context. Therefore Ctrl+S routes through Save As, and a newer or changed source file cannot be overwritten by recovery startup logic.

## Engineering boundary

CleanroomX produces screening and numerical/provenance evidence. It does not by itself establish ISO cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, physical/statistical uncertainty, or regulatory compliance. Applicable requirements and acceptance criteria remain external project inputs.
