# CleanroomX v0.102.1 Spatial Closure Test Evidence

Validation date: 2026-09-25

## Immutable base release

CleanroomX v0.102.0 is published at
`37a83dcce3489397647f27faf41a7c79680aa576`. The patch release does not
move or rewrite that tag.

## v0.102.1 behavior under qualification

The patch adds focused regression and installed-GUI coverage for:

- observed pressure-cascade delta derived only from supplied spatial room pressures;
- explicit pass/fail/available/unavailable relationship state against configured active-analysis minimum delta;
- synchronized relationship rendering in both 2D and 3D;
- source and packaged demo defaulting to the verification analysis;
- installed demo smoke proving representative three-room geometry renders in 2D and 3D and that pressure-cascade relationships render in both views.

The existing v0.102 spatial guarantees remain in scope: one canonical spatial model,
floor/opening metadata, stable room identity, persisted synchronization provenance,
all-or-nothing geometry-to-analysis mapping preflight, strict persistence validation,
undo/redo integration, and legacy schema-v1 compatibility.

## Release qualification contract

Publication is intentionally tied to the normal GitHub Actions CI workflow. The publisher
runs only after successful CI on `main`, then independently verifies that the successful
CI commit is still the current `main` commit before tagging v0.102.1.

The required CI includes the complete Python 3.11/3.12/3.13 suites, legacy solver/provenance
compatibility gates, application and Release 2 gates, clean-wheel installation, Windows
checkout launchers, representative CLI smoke, Python 3.13 performance evidence, and the
installed Tk/Xvfb `cleanroomx-gui --demo --smoke` path.

## Engineering boundary

No solver equation, numerical tolerance, no-extrapolation/root-selection rule, uncertainty
semantic, project schema version, unit convention, or engineering acceptance criterion is
intentionally changed by v0.102.1.
