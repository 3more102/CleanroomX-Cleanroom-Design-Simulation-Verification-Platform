# CleanroomX

[![CI](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/workflows/ci.yml/badge.svg)](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/workflows/ci.yml)
[![Security](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/workflows/security.yml/badge.svg)](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/workflows/security.yml)
[![Release](https://img.shields.io/badge/release-v0.102.1-blue)](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/releases/tag/v0.102.1)
![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)

**CleanroomX** is an engineering platform for cleanroom **design, simulation, verification, spatial planning, HVAC analysis, and auditable numerical evidence**.

The current stable release is **v0.102.1**.

## What CleanroomX provides

### 2D + 3D cleanroom design workspace

- One canonical spatial model shared by the synchronized 2D editor and 3D viewer.
- Floors, rooms, dimensions, elevations, classifications, doors, windows, transfer openings, and placed equipment/devices.
- Grid snapping, room movement and resize, viewport controls, fit/reset, 3D orbit, labels, pressure overlays, and pressure-cascade visualization.
- Spatial integrity checks for invalid geometry, overlapping rooms, duplicate names, orphan assignments, and invalid device placement.
- Project-wide transactional Undo/Redo.
- Deterministic spatial editing and no-op suppression to avoid unnecessary history/autosave changes.
- Validated, atomic property edits that keep devices attached when room coordinates change.
- Room/device duplication with fresh IDs, synchronized views, and one-step Undo/Redo.

### Engineering verification

CleanroomX includes engineering workflows for:

- room volume and air-change calculations;
- ACH, differential-pressure, and particle-concentration checks;
- multi-room pressure-cascade verification;
- recovery/particle-decay screening;
- psychrometric and thermal calculations;
- supply/return/exhaust/transfer airflow balance;
- preliminary fan duty and power calculations;
- duct pressure-loss analysis;
- branch, fixed-resistance, and looped airflow networks;
- fan/network operating-point solving;
- variable-friction network solving;
- bounded uncertainty and numerical provenance analysis.
- explicit design-requirements ↔ preliminary air-system consistency checks.
- explicit design pressure-target ↔ solved pressure-network node/reference consistency checks.
- versioned compliance rule-pack evidence checks with explicit source/reference traceability and SHA-256 binding for both criteria and supplied evidence revisions.
- design-assurance matrix composition across canonical design consistency, optional explicit pressure-design consistency, and versioned compliance evidence, with tamper-evident component/traceability digests.

#### Strict verification automation

Room and project verification expose both legacy no-failure semantics and strict completed-verification semantics. The default CLI exit code remains backward compatible: exit code 0 means no configured check recorded a failure, even if some evidence is still `not_checked`. For CI, release gates, or engineering automation that must reject incomplete evidence, use:

```bash
cleanroomx verify examples/basic_room.json --require-verified
cleanroomx verify-project examples/facility_project.json --require-verified
```

With `--require-verified`, exit code 0 requires `verified: true`; `pass_with_unchecked`, `not_checked`, and `fail` return exit code 2. The JSON result is unchanged and still includes `status`, `complete`, `verified`, `no_failures_detected`, and the backward-compatible `passed` field.

### Spatial ↔ engineering synchronization

Spatial and engineering data remain deliberately separated.

- Geometry synchronization is **dimension-only**.
- Changes are preflighted before mutation.
- CleanroomX tracks synchronized, geometry-newer, engineering-newer, conflicting, and unmapped states.
- Fresh verification pressure may drive 2D/3D pressure visualization without being written back into spatial geometry.

### Project requirements

- **Verify → Requirements Editor…** creates and edits canonical requirement sets inside CleanroomX.
- Requirements retain explicit source/revision, scope, criterion, units, tolerance, applicability, verification method, and evidence expectations.
- Candidate edits are validated against the complete project before commit, preventing mapped requirements from being silently orphaned.
- Requirement edits participate in project-wide Undo/Redo and feed the existing traceability, verification, ProofGraph, diagnostics, and reporting paths.

### Project constraints

- **Verify → Project Constraints…** provides an in-application Constraint Manager.
- Constraints reuse the versioned compliance rule-pack engine rather than a parallel evaluator.
- Each rule keeps an explicit evidence path, operator, expected value, unit, tolerance, source, and reference.
- Changes are validated transactionally and participate in project-wide Undo/Redo and autosave.
- CleanroomX does not infer regulatory acceptance criteria; project criteria remain explicit user/project data.

### Project integrity and evidence

- Strict JSON ingestion.
- Atomic project/report persistence.
- Autosave and crash-recovery artifacts.
- Saved project revisions and external-write protection.
- Immutable run snapshots and execution provenance.
- Deterministic project batch execution.
- Project-wide read-only design/model diagnostics with spatial, synchronization, input-validity, and stale-evidence checks.
- Portable project bundles and engineering reports.
- Deterministic self-verifying design-assurance snapshots that bind exact source bytes, normalized results, optional pressure-design evidence, and traceability digests.
- SHA-256 based numerical/provenance evidence for supported solver workflows.

## Quick start

### Windows — repository checkout

From PowerShell:

```powershell
cd C:\CleanroomX
.\start-cleanroomx.ps1
```

CMD is also supported:

```cmd
start-cleanroomx.cmd
```

Run the installation/readiness check:

```powershell
.\start-cleanroomx.ps1 --check
```

### Python installation

CleanroomX supports **Python 3.11, 3.12, and 3.13**.

```bash
python -m venv .venv
python -m pip install -e .
cleanroomx-gui
```

Open the packaged demonstration:

```bash
cleanroomx-gui --demo
```

Headless readiness check:

```bash
cleanroomx-gui --check
```

Run the full installation/runtime health check:

```bash
cleanroomx-doctor
```

Use `cleanroomx-doctor --format text` for a concise operator summary, `cleanroomx-doctor --require-bim` when native IFC/BIM support is mandatory, `cleanroomx-doctor --require-desktop` to prove a real hidden Tk desktop root can initialize and close cleanly, or `cleanroomx-doctor --deep` to execute the packaged demo's active analysis through the real application runner. Warning and failure checks now carry actionable remediation guidance in both JSON and text output. JSON remains the deterministic default for support tickets and CI evidence.

## Main command-line tools

Run a saved project:

```bash
cleanroomx-project-run project.cleanroomx.json
```

Create or verify portable project evidence:

```bash
cleanroomx-project-bundle --help
```

Freeze and independently replay design-assurance evidence:

```bash
cleanroomx-assurance-snapshot create examples/design_assurance_demo.json design_assurance.snapshot.json
cleanroomx-assurance-snapshot verify design_assurance.snapshot.json
```

See [Design Assurance Snapshots](docs/ASSURANCE_SNAPSHOTS.md) for schema, integrity, replay, and security boundaries.

Run a project-wide model/provenance health check:

```bash
cleanroomx-project-check project.cleanroomx.json
```

See [Project Diagnostics](docs/PROJECT_DIAGNOSTICS.md) for rule scope, severity, freshness behavior, and exit codes.

Compare two ProofGraph evidence revisions and surface downstream impact/staleness:

```bash
cleanroomx-proofgraph-diff baseline.proofgraph.json candidate.proofgraph.json --require-no-stale
```

Other installed CLIs cover HVAC, qualification, duct flow, loop networks, fan/network studies, uncertainty, consistency checks, and engineering dossiers.

## Validation

The **v0.102.1** release closure was validated across Python **3.11 / 3.12 / 3.13**.

Recorded release evidence includes:

- **1008 passing tests** on each supported Python version for the final deterministic-spatial-drag release gate;
- Windows PowerShell and CMD launcher smoke tests;
- clean wheel build/install checks;
- installed Tk GUI smoke testing;
- synchronized 2D/3D spatial regression coverage;
- autosave completion-race regression coverage;
- solver/provenance compatibility gates.

The exact release evidence is preserved in:

- [VALIDATION.txt](VALIDATION.txt)
- [TEST_EVIDENCE.md](TEST_EVIDENCE.md)
- [CHANGELOG.md](CHANGELOG.md)

## Engineering boundary

CleanroomX provides **engineering screening, simulation, verification, and software/provenance evidence**.

It does **not**, by itself, establish cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance.

## Documentation

- [Professional Engineering User & Validation Manual (PDF)](docs/CleanroomX_Complete_Solution_Manual_2026-09-30.pdf)
- [Professional manual source (Markdown)](docs/CleanroomX_Complete_Solution_Manual_2026-09-30.md)

- [Application & GUI](docs/APPLICATION_GUI.md)
- [2D + 3D spatial workspace](docs/LAYOUT_2D_3D.md)
- [Architecture](ARCHITECTURE.md)
- [Design assurance matrix](docs/DESIGN_ASSURANCE.md)
- [Design assurance snapshots](docs/ASSURANCE_SNAPSHOTS.md)
- [Pressure design consistency](docs/PRESSURE_DESIGN_CONSISTENCY.md)
- [Deployment](DEPLOYMENT.md)
- [Migration notes](MIGRATIONS.md)
- [Security](SECURITY.md)
- [Production acceptance contract](docs/PRODUCTION_ACCEPTANCE.md)
- [ProofGraph revision diff and change impact](docs/PROOFGRAPH_CHANGE_IMPACT.md)
- [Rollback](ROLLBACK.md)
- [Changelog](CHANGELOG.md)

## Release

**Latest stable:** [CleanroomX v0.102.1](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/releases/tag/v0.102.1)
