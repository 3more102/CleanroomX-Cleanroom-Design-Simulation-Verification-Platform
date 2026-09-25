# CleanroomX

[![CI](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/workflows/ci.yml/badge.svg)](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/actions/workflows/ci.yml)
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

### Spatial ↔ engineering synchronization

Spatial and engineering data remain deliberately separated.

- Geometry synchronization is **dimension-only**.
- Changes are preflighted before mutation.
- CleanroomX tracks synchronized, geometry-newer, engineering-newer, conflicting, and unmapped states.
- Fresh verification pressure may drive 2D/3D pressure visualization without being written back into spatial geometry.

### Project integrity and evidence

- Strict JSON ingestion.
- Atomic project/report persistence.
- Autosave and crash-recovery artifacts.
- Saved project revisions and external-write protection.
- Immutable run snapshots and execution provenance.
- Deterministic project batch execution.
- Project-wide read-only design/model diagnostics with spatial, synchronization, input-validity, and stale-evidence checks.
- Portable project bundles and engineering reports.
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

## Main command-line tools

Run a saved project:

```bash
cleanroomx-project-run project.cleanroomx.json
```

Create or verify portable project evidence:

```bash
cleanroomx-project-bundle --help
```

Run a project-wide model/provenance health check:

```bash
cleanroomx-project-check project.cleanroomx.json
```

See [Project Diagnostics](docs/PROJECT_DIAGNOSTICS.md) for rule scope, severity, freshness behavior, and exit codes.

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

- [Application & GUI](docs/APPLICATION_GUI.md)
- [2D + 3D spatial workspace](docs/LAYOUT_2D_3D.md)
- [Architecture](ARCHITECTURE.md)
- [Deployment](DEPLOYMENT.md)
- [Migration notes](MIGRATIONS.md)
- [Security](SECURITY.md)
- [Rollback](ROLLBACK.md)
- [Changelog](CHANGELOG.md)

## Release

**Latest stable:** [CleanroomX v0.102.1](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/releases/tag/v0.102.1)
