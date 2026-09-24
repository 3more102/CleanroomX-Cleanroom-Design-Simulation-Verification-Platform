# CleanroomX Architecture

## Release scope

CleanroomX v0.100.0 is a Python 3.11+ engineering screening, simulation, verification, uncertainty/provenance, HVAC, fan/network, qualification, and reporting platform. The desktop application is an operator shell over the same validated backend modules used by the command-line tools.

## Layers

1. **Engineering backends** — calculation, solver, uncertainty, qualification, HVAC, fan/network, dossier, consistency, and report modules under `src/cleanroomx/`.
2. **Application service registry** — `src/cleanroomx/application.py` declares 25 GUI-exposed workflows and binds each workflow to fixed parser, runner, and reporter functions. `validate_application_registry()` resolves those bindings before use.
3. **Project persistence** — `src/cleanroomx/project.py` implements the `cleanroomx.project` schema, strict JSON validation, legacy migration, duplicate-id and active-analysis checks, and atomic temporary-file replacement on save.
4. **Desktop UI** — `src/cleanroomx/gui.py` provides project lifecycle, JSON editing, validation, non-blocking execution, per-analysis result ownership, diagnostics, reporting, export, plotting, dirty-state tracking, unsaved-change protection, and active-run mutation guards.
5. **CLI entry points** — `pyproject.toml` exposes the main CleanroomX command plus dedicated HVAC, recovery, uncertainty, qualification, network, fan, dossier, consistency, and GUI commands.
6. **Verification/provenance** — solver-specific modules retain compatibility, replay, integrity, residual, convergence, coverage, and deterministic reporting evidence. CI preserves explicit v0.91-v0.95 compatibility gates before running the complete suite.

## Desktop data flow

A project file is loaded through `load_project_document()` and migrated only when it matches a supported legacy shape. The active analysis input is parsed by the registry-selected backend parser, executed by the registry-selected backend runner, normalized to strict JSON, and rendered through the backend reporter when available. Result ownership remains tied to the analysis id so stale results are not silently reassigned after edits, deletion, or analysis switching.

Project saves serialize schema version 1 and validate the resulting document before an atomic replace. Unsupported future schema versions are rejected instead of guessed.

## Engineering boundary

CleanroomX produces screening and numerical/provenance evidence. It does not by itself establish ISO cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, physical or statistical uncertainty, or regulatory compliance. Applicable requirements and acceptance criteria remain external project inputs.
