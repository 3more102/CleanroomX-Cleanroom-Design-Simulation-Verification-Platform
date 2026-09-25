# CleanroomX v0.101 Release 2 Test Evidence

## Verified release target

Validation date: **2026-09-25**

Final Release 2 target merged on `main`:

`0f487a7e11ad81c8bcd54eb91b6420a1d46523ea`

Final verification gate:

- PR **#431 — Release 2 final v0.101.0 consolidation**
- Exact tested PR head: `993a2803e1af6a37af05ac0036948cc9f7fb3fce`
- Exact tested tree: `a6900bc9525721d964498b70c5da68950d7d6fba`
- Pull-request CI: run **#1463**, run id `36162913321`
- CI conclusion: **SUCCESS**
- Final merged commit: `0f487a7e11ad81c8bcd54eb91b6420a1d46523ea`
- Final merged tree: `a6900bc9525721d964498b70c5da68950d7d6fba`

The merged release-target tree is byte-for-byte the same Git tree that passed the final PR CI gate.

## Full matrix evidence

The complete suite passed on every supported interpreter:

- Python 3.11: **960 passed**
- Python 3.12: **960 passed**
- Python 3.13: **960 passed**

Every interpreter also passed:

- focused application/desktop/input-contract gate: **291 passed**
- Release 2 consolidation gate: **128 passed**
- v0.91-v0.95 compatibility gates

## Packaging, CLI, desktop, and performance evidence

Every Python 3.11/3.12/3.13 matrix job:

- built `cleanroomx-0.101.0-py3-none-any.whl`;
- installed the wheel into a clean environment;
- passed installed `cleanroomx-gui --check`;
- verified packaged demonstration/resources;
- passed installed `cleanroomx-project-run` smoke;
- passed representative CLI smoke coverage.

Python 3.13 additionally passed:

- Release 2 performance evidence;
- installed Tk/Xvfb `cleanroomx-gui --demo --smoke`.

## Release 2 application scope covered by the verified tree

The verified v0.101 tree includes:

- a synchronized 2D/3D spatial design workspace backed by one canonical project model;
- room creation, selection, movement, resizing, pressure display, and device placement;
- derived 3D geometry with azimuth/elevation/zoom/pan/fit controls;
- spatial validation for overlapping/duplicate rooms and invalid/orphan device placement;
- spatial persistence, legacy-safe project handling, and application-wide bounded undo/redo;
- strict project and engineering JSON ingestion;
- guarded durable project writes, revisions, autosave, and crash recovery;
- plugin API v1 and application registry integrity validation;
- immutable run evidence and run-history integrity;
- external-dependency freshness and source-revision protection;
- verified portable project bundles and self-contained engineering HTML reports;
- deterministic project batch automation;
- precision-safe HVAC/duct/branch/fan/thermal composition;
- numerical-integrity and solver-provenance compatibility gates.

## Engineering boundary

Release 2 does not intentionally change validated solver equations, numerical tolerances, no-extrapolation/root-selection behavior, uncertainty enumeration semantics, project schema version, unit conventions, or engineering acceptance criteria.

The desktop and reports remain engineering screening, calculation, and traceability tools. They do not by themselves establish cleanroom certification, CFD validity, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance.
