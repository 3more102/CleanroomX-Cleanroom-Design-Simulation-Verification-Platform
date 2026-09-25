# CleanroomX v0.102.0 Spatial Closure Test Evidence

## Verified functional baseline

Validation date: 2026-09-25

The synchronized 2D/3D spatial implementation was merged to `main` by PR **#436 — Finish synchronized CleanroomX 2D/3D spatial design**.

- Merged main commit: `d4b8f6294dd7deed207935423a52cf5f19a035eb`
- Post-merge GitHub Actions CI: **run #1493 / id 36167376732**
- Conclusion: **success**
- Python 3.11 complete suite: **973 passed**
- Python 3.12 complete suite: **973 passed**
- Python 3.13 complete suite: **973 passed**
- Windows PowerShell launcher smoke: **success**
- Windows CMD launcher smoke: **success**
- Python 3.13 performance evidence: **success**
- Clean wheel build/install and installed application checks: **success**
- Python 3.13 Tk/Xvfb `cleanroomx-gui --demo --smoke`: **success**
- Representative CLI smoke checks: **success**

## Spatial behavior covered

The verified tree includes:

- one canonical `project.metadata.spatial_layout` model consumed by both views;
- backward-compatible floor metadata and deterministic legacy defaults;
- room elevation, classification, stable analysis-room linkage, dimensions, and pressure display;
- door and transfer-opening geometry plus width, height, wall side, orientation, and swing metadata;
- synchronized room/device drag, room resize, keyboard nudge, optional grid snapping, selection, zoom, pan, fit, and 3D camera controls;
- independently switchable pressure, labels, devices, and relationship overlays;
- pressure-cascade arrows derived only from explicit active-analysis `pressure_cascade` records;
- deterministic layout area, volume, room-count, and device-count metrics;
- explicit geometry-to-analysis synchronization with duplicate/missing-link rejection;
- strict persistence-boundary spatial validation and interactive overlap/orphan/out-of-room/opening placement diagnostics;
- representative Process / Preparation / Ante source and packaged demo geometry.

## Release identity

The published `v0.101.0` tag remains unchanged at
`1ca79b66c2e87c7ab45745ee98a5f60efa444cf5`.

The `v0.102.0` release metadata changes only release/package/demo identity and documentation around the already-verified spatial tree. The normal CI workflow reruns the full Python 3.11/3.12/3.13 matrix, installed-wheel verification, launcher checks, performance evidence, GUI smoke, and CLI smoke before merge. The release publisher runs only after a successful current-main CI result and refuses to publish a stale main commit.

## Engineering boundary

No solver equation, numerical tolerance, no-extrapolation/root-selection rule, uncertainty semantic, project schema version, unit convention, or engineering acceptance criterion is intentionally changed by the v0.102.0 closure.
