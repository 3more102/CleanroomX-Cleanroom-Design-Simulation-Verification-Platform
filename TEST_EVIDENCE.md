# CleanroomX v0.102.1 Final Spatial Production Closure Test Evidence

## Verified final baseline

Validation date: 2026-09-25

## v0.102.1 final spatial production baseline

The final post-v0.102 spatial code is covered by three sequential, CI-green closures on current main:

- PR **#467 — Close final CleanroomX spatial production gaps**
  - exact tested head: `4be4fb840480df7a5f1e0313a73830313150d9dd`
  - PR CI **#1540** / id `36170548238`: **success**
  - merged main commit: `9a9caedb46b80d376c21f36e3b10f46b05e00764`
  - post-merge main CI **#1550** / id `36171324227`: **success**
- PR **#472 — Finish remaining CleanroomX spatial production capabilities**
  - exact tested head: `8a34c3d649aee54c377b4194a6d619559d219421`
  - PR CI **#1551** / id `36171758793`: **success**
  - merged main commit: `f595aaba6e7b8704beb62acc04f0eb4d036d8f09`
- PR **#473 — Finish CleanroomX 3D fit-to-view**
  - exact tested head: `332eb07ed1d4d27a028d7fe8886b3914da29c8d7`
  - PR CI **#1552** / id `36171783101`: **success**
  - merged main commit: `1fc662441763fd6bd2070aac6d6449410f06fb2a`

Those successful CI jobs exercise the complete Python 3.11/3.12/3.13 suite, clean-wheel installation, representative CLI checks, Windows checkout launchers, and the Python 3.13 performance plus installed Tk/Xvfb GUI smoke defined by the repository CI workflow.

The final closure keeps one canonical persisted spatial model; makes engineering synchronization bidirectional but dimension-only; projects fresh current verification pressure into visualization without persisting solver evidence into geometry; uses the same evidence for 2D/3D cascade state; supports windows and generic wall openings; centralizes deterministic viewport transforms; computes true 3D fit-to-view zoom/pan from room floor and ceiling geometry; and strengthens the packaged-demo smoke. No solver equation, numerical tolerance, project schema version, or engineering acceptance criterion is intentionally changed.


## v0.102.0 final synchronized spatial baseline

- PR **#442 — Complete spatial engineering synchronization state**
- Exact tested PR head: `db9169555127b1799f261f31113d18cdaf2518ed`
- Merged `main` commit: `2c8d0696170080d5c333ff1fc809f671aec1ac1d`
- Exact tested and merged Git tree: `af3c534599ee0921f8f21c8a14bd7b6b3e209258`
- PR CI run **#1503** / id `36168565655`: **success**
- Focused spatial-design gate: **41 passed**
- Python 3.11 complete suite: **985 passed**
- Python 3.12 complete suite: **985 passed**
- Python 3.13 complete suite: **985 passed**
- Release 2 consolidation gate: **131 passed**
- application/desktop/input-contract/strict-ingestion/project-batch gate: **291 passed**
- Windows PowerShell/CMD checkout launcher smoke: **success**
- Python 3.13 installed Tk/Xvfb desktop smoke: **CleanroomX GUI smoke: PASS**
- Clean wheel build/install: **success** on Python 3.11, 3.12, and 3.13

The tested PR head and the squash-merged `main` commit have the same Git tree. The release-identity bump to 0.102.0 is intentionally metadata/publishing-only and must pass the same CI matrix before merge and again on `main` before the immutable tag is published.

The spatial closure adds persisted synchronization provenance and deterministic room states (**synchronized**, **geometry newer**, **engineering newer**, **conflicting**, **unmapped**), fail-closed ambiguity handling, persistence validation, all-mappings preflight before mutation, UI visibility, and focused transform/zoom regressions without changing validated solver semantics.


Final Release 2 merge on `main`:

`0f487a7e11ad81c8bcd54eb91b6420a1d46523ea`

Final release-consolidation pull request:

- PR **#431 — Release 2 final v0.101.0 consolidation**
- Exact PR head tested: `993a2803e1af6a37af05ac0036948cc9f7fb3fce`
- Exact tested Git tree: `a6900bc9525721d964498b70c5da68950d7d6fba`
- Final merged `main` commit: `0f487a7e11ad81c8bcd54eb91b6420a1d46523ea`
- Final merged Git tree: `a6900bc9525721d964498b70c5da68950d7d6fba`
- Pull-request GitHub Actions run **#1463**
- Run id: `36162913321`
- Conclusion: **success**
- Post-merge `main` push CI run **#1464** / id `36163451603`: **success** on Python 3.11, 3.12, and 3.13

The tested PR tree and merged `main` tree are byte-for-byte identical.

The merged final tree includes the strict engineering JSON boundary merged through #430, deterministic project-level batch execution, the remaining project-batch Markdown presentation hardening, and synchronized v0.101.0 package/runtime/demo/test/CI release identity.

## Final Windows checkout / 2D+3D launcher closure

PR **#434 — Add PATH-independent Windows launcher for CleanroomX 2D/3D** completed the repository-checkout usability gap after the Release 2 code consolidation.

- Exact PR head: `9f5d0f654c2016096fb1fb2cbdb5d4395e91d645`
- Merged `main` commit: `1acbaa1b67f624ae495590f78d5bccfc038fbd82`
- Pull-request CI run **#1472** / id `36164491604`: **success**
- Python 3.11 complete suite: **961 passed**
- Python 3.12 complete suite: **961 passed**
- Python 3.13 complete suite: **961 passed**
- Windows `windows-latest` PowerShell launcher smoke: **success**
- Windows `windows-latest` CMD launcher smoke: **success**
- Python 3.13 installed Tk/Xvfb desktop smoke: **CleanroomX GUI smoke: PASS**

The launcher executes the repository `src` tree directly, prefers `.venv\\Scripts\\python.exe`, and defaults to `--demo`, avoiding stale installed-package/PATH ambiguity while exposing the synchronized Design 2D + 3D workspace. No solver equation, tolerance, engineering acceptance rule, project schema, spatial model, or analysis behavior changed in PR #434.

## Release 2 consolidation matrix evidence

The complete test suite passed on every supported interpreter in final-tree run #1463:

- Python 3.11: **960 passed**
- Python 3.12: **960 passed**
- Python 3.13: **960 passed**

Each matrix job also passed the compatibility and release gates:

- v0.95 solver-result-integrity compatibility: **7 passed**
- v0.94 canonical solver-provenance compatibility: **5 passed**
- v0.93 supplied-point network-state replay compatibility: **10 passed**
- v0.92 compatibility: **15 passed**
- v0.91 compatibility: **8 passed**
- application/desktop/input-contract/strict-ingestion/project-batch gate: **291 passed**
- Release 2 consolidation gate: **128 passed**

## Packaging, batch, CLI, desktop, and performance evidence

Every Python 3.11/3.12/3.13 matrix job:

- built and installed the CleanroomX **0.101.0** wheel in a clean virtual environment;
- passed installed `cleanroomx-gui --check`;
- verified packaged demonstration resources;
- verified the installed `cleanroomx-project-bundle` entry point;
- executed the installed `cleanroomx-project-run` against the packaged demonstration project and validated the emitted project-batch schema, selected analysis id, and completed-count evidence;
- passed representative nonlinear loop, uncertainty, and dossier CLI JSON/Markdown smoke checks;
- confirmed package metadata and runtime `cleanroomx.__version__` agree at **0.101.0**.

Python 3.13 additionally passed:

- Release 2 spatial-validation performance evidence;
- Release 2 project-bundle performance evidence;
- installed Tk/Xvfb `cleanroomx-gui --demo --smoke`, reported as **CleanroomX GUI smoke: PASS**.

The project-bundle benchmark completed small, medium, large, and stress cases. The stress case used a **33,554,432-byte** dependency and completed export, verification, and extraction without a validation failure.

## Release 2 scope covered by the verified tree

The tested tree includes the consolidated Release 2 architecture and final correctness hardening:

- isolated project-model snapshots and lossless same-schema extension preservation;
- stable analysis/spatial identity and strict project/spatial validation;
- durable verified atomic persistence and guarded project writes;
- session-isolated autosave, integrity-checked recovery, and protected legacy migration saves;
- bounded project/spatial undo-redo and guarded saved-project revision history;
- versioned analysis plugin API v1;
- isolated single-parse execution and immutable external-input/run evidence;
- persisted integrity-checked run history and dependency/staleness tracking;
- verified portable project bundles and self-contained engineering HTML reports;
- deterministic project-level batch execution with exact source-revision checks, per-analysis isolation, preserved run provenance, strict/atomic reporting, and installed-wheel smoke coverage;
- strict engineering JSON ingestion that rejects non-finite constants and duplicate object keys before model construction or solver execution;
- precision-safe HVAC/duct/branch/fan/thermal composition;
- explicit verification aggregate status/completeness;
- Markdown report and project-batch presentation-boundary escaping;
- finite-number validation at foundational engineering calculation boundaries;
- synchronized v0.101.0 package, runtime, demo, test, and CI release identity.

The v0.91-v0.95 compatibility suites remain green on the same final tree. No solver equation, numerical tolerance, no-extrapolation/root-selection rule, uncertainty semantic, project schema version, engineering acceptance criterion, or unit convention was intentionally changed by the final release-identity and presentation-boundary closure.

CleanroomX provides engineering screening, simulation, verification, and software/provenance evidence; it does not by itself establish cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance.
