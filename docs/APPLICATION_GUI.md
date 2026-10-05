# CleanroomX Desktop Application

CleanroomX v0.101 provides a Tkinter desktop application over the same parsers, solvers, uncertainty engines, consistency checks, and report generators used by the command-line workflows. The GUI is an application shell over the validated backend; it does not duplicate or replace the engineering calculation implementations.

## Install and launch

Install the package for normal use:

```bash
python -m pip install .
```

For development and tests:

```bash
python -m pip install -e .[dev]
```

Launch a new project:

```bash
cleanroomx-gui
```

Open the self-contained demonstration project shipped inside the installed package:

```bash
cleanroomx-gui --demo
```

On Windows, a repository checkout can launch the current source tree without relying on the console-script PATH:

```powershell
.\start-cleanroomx.ps1
```

The launcher prefers `.venv\Scripts\python.exe`, sets the repository `src` directory for imports, and defaults to `--demo`, which exposes the synchronized **Design 2D + 3D** workspace. `.\start-cleanroomx.cmd` provides the same behavior from PowerShell, Command Prompt, or Explorer.

Check that the application layer, GUI imports, and every declared parser/runner/reporter binding are usable without opening a window:

```bash
cleanroomx-gui --check
```

The headless check validates the application registry as an executable contract before reporting readiness. It rejects duplicate keys, catalog/mapping drift, invalid parser/runner contracts, and unresolved/non-callable targets. Normal GUI startup performs the same validation before creating the Tk root.

For CI or Linux automation with a virtual display:

```bash
xvfb-run -a cleanroomx-gui --demo --smoke
```

## Project format

Desktop projects use the `cleanroomx.project` JSON schema. Schema version 1 stores project metadata, an ordered list of analyses, and an optional active analysis identifier. Each analysis stores a stable id, display name, backend analysis kind, and backend input JSON.

Project saves are validated before writing and use an atomic temporary-file replacement. The loader rejects unsupported future schema versions, duplicate analysis ids, invalid active-analysis references, malformed JSON, and non-finite JSON constants such as `NaN` or `Infinity`. Supported legacy single-analysis shapes are migrated into the current document model on load. Within supported schema version 1, unrecognized additive fields at the document, project, and analysis-record levels are retained as opaque strict-JSON data across open/edit/save round trips instead of being silently discarded. CleanroomX-owned fields remain authoritative.

### Protected legacy conversion

When one of the supported legacy formats is opened, the desktop displays it as a migrated unsaved copy rather than treating the in-memory schema-v1 model as a normal saved project. The original legacy path remains available for resolving relative engineering references, but **Save Project** routes to **Save Project As**. The first Save As must use a different path; CleanroomX refuses the legacy source itself. Cancelled or failed saves keep that protection active. Only a successful validated schema-v1 save elsewhere clears the migration protection.

### External-change write protection

When a saved project is opened, CleanroomX records a stable content revision using the normalized path, size, modification timestamp, and SHA-256 digest. Revision-aware loading derives the SHA-256 and byte size from the exact bounded strict-JSON byte snapshot passed to parsing, rather than from a separate fingerprint read, and rejects observed opened-file or live-path revision changes during that snapshot. **Save Project** is an optimistic guarded write: the destination must still match the content revision that was opened or produced by the previous successful save. The guard is checked before serialization and again immediately before the atomic replace.

If another CleanroomX window or external editor changes, deletes, or replaces the project file, the save is blocked and the newer on-disk file is preserved. The application directs the operator to **Save Project As** to preserve the current window's work under another name, or to reopen the project to accept the disk version. Selecting the already-open project path through **Save Project As** does not bypass the guard. Timestamp-only metadata changes with identical file content do not create a false conflict.

For a genuinely different Save As destination, CleanroomX captures the destination revision after the file chooser returns and applies the same guarded replace, protecting against a race where another process changes or creates the target before the atomic commit. Save As also refuses destinations that alias declared external engineering dependencies, including existing hard-link aliases, and repeats that dependency-identity check immediately before atomic replacement so a late destination substitution cannot overwrite an engineering input.

## Recovery autosave

The desktop application maintains crash-recovery autosaves separately from explicit project files. Dirty edits schedule an idle-debounced recovery checkpoint after 1.5 seconds, while the 60-second periodic sampler remains a fallback for long-lived dirty sessions. Rapid edits reset the short checkpoint so typing and drag gestures coalesce instead of generating one file per event. Use `--autosave-interval-seconds N` to change the periodic fallback interval or `0` to disable recovery autosave entirely. The right side of the status bar reports whether autosave is ready, saving, saved, clean, or failed.

Autosave never writes to the open `.cleanroomx.json` path. It writes a versioned `cleanroomx.autosave` recovery envelope in the per-user recovery directory using the same atomic-write primitive as project persistence. Writes run on a single background worker, identical snapshots are suppressed, newer pending edits are coalesced, and history is bounded per project identity.

Each artifact contains the recoverable project snapshot, the active raw editor draft, application version, recovery timestamp, project identity, and a source-file fingerprint containing path, size, modification time, and SHA-256.

Recovery artifacts are capped at 128 MiB, twice the normal 64 MiB project-file ceiling. The autosave writer refuses to publish an artifact above that ceiling, and the reader uses CleanroomX's canonical bounded strict-JSON file-ingestion boundary with the recovery-specific ceiling and opened-file/live-path revision checks. Oversized, invalid-UTF-8, duplicate-key, non-finite, replaced, disappeared, or revision-changing recovery inputs fail closed as recovery-format errors. A malformed JSON editor draft is preserved as raw text without being promoted into the authoritative project model. The recovery scanner reports malformed artifacts explicitly and classifies the source project as unchanged, changed, missing, or newer. This foundation never automatically overwrites a newer project file. During semantic recovery comparison, the preserved raw editor draft is reparsed through CleanroomX's canonical strict JSON boundary, so duplicate object keys, non-finite constants, and other strict-parser failures remain invalid recovery evidence instead of being silently normalized by permissive JSON parsing.

Current-session recovery artifacts are invalidated after an explicit save or an explicit discard. Recovery files from older sessions are not silently deleted by merely opening or saving the same project.

### Startup recovery

On normal interactive startup, CleanroomX scans the recovery directory before opening a command-line project argument. If recovery data exists, **Recovery Center** lists the project name, exact UTC recovery timestamp, source comparison state, and original source path. **Inspect…** shows the project identity, application version, recovered analysis list, raw editor draft, and a deterministic semantic comparison against the current source project. The comparison reports changed project fields, recovery-only/source-only analyses, modified analyses, active-analysis changes, and editor-draft divergence. Missing or invalid source files are reported as non-comparable rather than guessed or auto-merged. Malformed/unreadable recovery artifacts are reported and preserved.

**Restore as Unsaved Copy** never writes or rebinds the original project file. The recovered project opens dirty with **Save Project As** required. If the recovery came from a saved project, CleanroomX retains that original path only as read/context so relative consistency/dossier references still resolve correctly. The first recovered Save As refuses that original source path, forcing the recovered work to a different file so both versions remain available. After a successful Save As, the new explicit file is durable before the restored recovery artifact is removed.

**Discard Recovery** deletes only the selected validated artifact inside the recovery directory and never modifies the source project. The same Recovery Center remains available from the File menu. Automated `--smoke` launch deliberately skips the interactive startup chooser.

## Operator workflow

1. Create a new project or open an existing `.cleanroomx.json` project.
2. Add an analysis from the application catalog, or select an existing analysis.
3. Edit or import the analysis input JSON. The editor accepts strict JSON objects only; non-finite constants such as `NaN` and `Infinity` are rejected.
4. Use **Validate** to run the real backend parser/validation path.
5. Use **Run** to execute the real backend workflow in a worker thread while keeping the UI responsive.
6. Inspect normalized JSON results, diagnostics/provenance evidence, Markdown reporting, and available plots.
7. Export input/result JSON, complete run-bundle JSON, or report Markdown and save the project. Writes are atomic and filesystem errors are surfaced in the GUI. Generic exports refuse destinations that alias the saved project source, a retained recovery source, or declared file-backed engineering dependencies; those identities are checked again immediately before atomic replacement.

The **Abandon** action suppresses the pending result but does not force-terminate Python threads. The application keeps the run exclusive and input locked until that worker actually exits, so abandoning a long computation cannot create overlapping backend runs. The status line reports both the waiting and worker-finished states.

Removing an analysis also clears any retained result owned by that analysis, preventing stale result/report export after deletion.

## Supported workflows

The application catalog is built from the shared backend registry and includes room/project verification, HVAC analysis, recovery qualification, room/qualification/thermal/psychrometric uncertainty, parallel/loop/variable-friction networks, fan operating-point and speed studies, fan-network integrations, fan/loop uncertainty, nonlinear fan/variable-friction loop analysis and uncertainty, damper studies, cross-module consistency, and engineering dossiers.

Consistency and dossier workflows resolve relative file references against project path context. Imported JSON is rebased from its source directory, and **Save Project As** rebases relative references when the destination directory changes. Absolute-only dossier inputs can run before the project is saved; relative references still require an explicit base directory. The installed `--demo` project ships its referenced files beside the project file.

## Spatial design workspace

The main notebook now includes **Design 2D + 3D**, a synchronized cleanroom layout workspace backed by project metadata. It is intentionally separate from the engineering solver implementations: spatial edits do not silently change analysis inputs.

The desktop shell now presents that capability as a professional engineering workspace rather than a flat analysis/form layout. A hierarchical **Project Navigator** groups the building/floor/rooms, devices, HVAC, pressure network, analyses, requirements, ProofGraph, evidence, and reports. Room/device selection is synchronized between the navigator and the design workspace. The design surface provides explicit **2D**, **3D**, and **Split** modes (Ctrl+1/Ctrl+2/Ctrl+3) so either viewport can use the primary screen area instead of being permanently compressed beside the other. The properties inspector is grouped by geometry, cleanroom, identity, and placement context, and hides fields that do not apply to the current spatial object. A compact **Guided Workflow** strip keeps the common path visible as **Design → Inputs → Validate → Run → Save & Verify → Report**, while the full menus, command palette, 2D/3D controls, diagnostics, and advanced engineering tools remain available.

The 2D view supports room creation, selection, drag movement with metric grid snapping, property editing and resizing, deletion, zoom, pan, fit-to-view, coordinate feedback, and placement of doors, FFUs, supply points, returns, exhausts, equipment, sensors, and transfer openings. The professional 2D interaction layer adds hover highlighting, a live grid snap crosshair, selected-room dimension annotations, and a right-click context menu for properties, duplication/deletion, doors/openings/devices, and analysis linking. Right-click is reserved for contextual commands; middle-button drag remains the pan gesture. Selected rooms expose a drag resize handle; floor name/elevation/default ceiling height and grid spacing are edited through **Floor…**. Snap-to-grid, pressure color, labels, devices, and pressure-cascade relationship arrows can be toggled independently. Drag translation is computed from immutable gesture-start coordinates, so snapped final geometry does not depend on intermediate mouse-motion event sampling. A click/release or drag that returns to the starting geometry is a no-op and does not dirty the project, record undo history, or schedule autosave. Spatial model edits participate in the same bounded application-wide transactional **Undo/Redo** stream as analysis and project edits: add, delete, property changes, and a full drag gesture are each one transaction; redo is invalidated by a new divergent edit, and undo/redo restores selection without rewinding the current camera/view state. The spatial toolbar delegates to that same global history, with Ctrl+Z, Ctrl+Y, and Ctrl+Shift+Z available while a spatial canvas has focus. When room pressure is present in a verification input, the layout visualizes only that supplied pressure data; it does not invent pressure values.

Detailed controls, persistence behavior, spatial metadata, and limitations are documented in [LAYOUT_2D_3D.md](LAYOUT_2D_3D.md).

The 3D view is generated from the same canonical spatial model as the 2D layout. Room dimensions, labels, selection, and devices therefore stay synchronized. The view supports azimuth rotation, elevation adjustment, zoom, pan, reset, and fit behavior without adding a third-party rendering dependency.

For room-verification and multi-room project-verification analyses, **Sync dimensions to active analysis** explicitly copies room dimensions (and an existing observed-pressure field when present) from the spatial model into the analysis JSON. Other engineering fields such as airflow, ACH requirements, particle requirements, and pressure-cascade criteria are preserved. Results for a synchronized analysis are invalidated and must be validated/run again.

Existing projects remain schema-version-1 compatible because the spatial document is stored under the existing project metadata block. If no spatial metadata exists, CleanroomX can seed a layout from real room geometry found in a verification analysis. Projects with no such geometry remain empty until the operator adds rooms.

## Engineering problems and verification workspace

The main engineering workspace includes a persistent bottom output pane with **Problems**, **Diagnostics**, **Verification**, **Console**, **Evidence**, **Results**, and **Report** views. The **Problems** view is not a second diagnostics engine: it presents the canonical deterministic `analyze_project_diagnostics()` result as an IDE-style table with severity, rule code, description, affected object, level context when available, and source category.

Problems can be searched and filtered by severity, diagnostic category, and affected object type. Columns are sortable, the panel reports visible/total issue counts, and Previous/Next plus F4/Shift+F4 provide keyboard-first triage. A context menu exposes locate/copy/navigation actions without changing diagnostic state. Double-clicking a spatial issue selects the referenced room or device, activates the design workspace, and fits the affected object in the synchronized 2D/3D views. Analysis-level issues navigate to the existing analysis input editor. Export uses the same canonical diagnostics payload and Markdown renderer as the project diagnostics CLI.

The **Verification** view summarizes current verification-currency state from the existing verification authority; the **Evidence** view lists retained project-verification records without recomputing historical verdicts. These views are read-only projections over existing domain services and do not change solver, requirement, ProofGraph, or acceptance semantics.

## ProofGraph explorer

The **ProofGraph** workspace reads only ProofGraph documents retained in the canonical project-verification history. Before a graph is rendered, CleanroomX reparses it with the canonical `proofgraph_from_dict()` validator. Digest tampering, broken source/evidence references, invalid provenance, inconsistent finding/verdict closure, or invalid verification-run relationships therefore fail closed instead of being visualized as trusted evidence.

The explorer provides a tree, an interactive graph, and a node-detail view. It projects requirements, CleanroomX model-object references, IFC identities, evidence sources, originating calculations, evidence/results, checks, findings, verdicts, and verification runs without recomputing any solver result or compliance verdict. Filters cover requirements, evidence, calculations, IFC, verification, failures, and unresolved evidence while retaining immediate graph context. A live search matches persisted node identity, labels, status, flags, and canonical node payloads, then keeps immediate trace neighbors visible so the result remains interpretable. The evidence-readiness strip reports persisted evidence-to-check links, unresolved findings, and retained verdict status counts; it is a presentation summary only and never substitutes for the canonical verdict. Double-clicking a node that carries a CleanroomX entity or subject reference selects that room/device in the shared spatial workspace and fits it in the synchronized engineering views.

The Project Navigator **ProofGraph** entry activates this workspace. Graph selection is digest-aware and duplicate retained documents are collapsed by canonical `graph_sha256`. Invalid retained evidence is cleared from the viewer and reported through the existing evidence/status surfaces rather than silently accepted.

## Professional inspection and recovery browsers

The analysis picker, retained run history, project verification history, requirements traceability, IFC re-import review, saved revisions, and recovery center use consistent dense inspection patterns: search, domain-specific filters, visible/total counts, keyboard navigation, deliberate no-match states, horizontal scrolling for wide engineering records, and read-only canonical detail views where applicable.

These surfaces do not synthesize engineering values. Run and verification history display retained evidence; verification currency comes from the existing currency assessment; requirements/mappings are read-only projections of canonical registries; IFC re-import review displays the deterministic re-import plan; and recovery/revision browsers operate only on already validated recovery/revision records.

The Start Center recent-project table can be searched by project name, path, or modification text. **Remove from Recent** removes only the remembered entry and never deletes the project file.

## Results and plots

All backend outputs are normalized to strict JSON with non-finite values rejected. Successful runs record canonical application-input SHA-256 provenance; consistency/dossier runs also capture before/after SHA-256, byte-size, and nanosecond modification-time evidence for external dependencies. Diagnostics exposes this evidence and **Export Run Bundle JSON** preserves the completed run data.

For `consistency` and `dossier`, those external dependencies are guarded as engineering run inputs rather than treated as advisory provenance only. CleanroomX fingerprints each referenced file from a stable read before execution and again after result/report generation. If a referenced file changes, disappears, or remains unstable while being fingerprinted, the run fails with an actionable error and the result is discarded. Stabilize the source files and run again. This prevents the desktop from presenting a result assembled while its external engineering inputs were changing; it does not lock files against other programs.

Cached desktop results are also bound to the canonical SHA-256 of the exact submitted analysis input. Before a cached result is restored, before a completed background run is accepted, and before result/run-bundle/report export, CleanroomX compares that recorded identity with the current analysis kind and input. A mismatch clears the cached result and requires a rerun. The existing immediate invalidation hooks remain in place, but the provenance check is the final fail-closed boundary if a mutation path misses an invalidation notification.

Runtime implementation provenance fingerprints the installed CleanroomX Python source tree before and after analysis execution. Source capture is fail-closed and resource-bounded: an individual Python source file may contribute at most 16 MiB and the complete source tree at most 128 MiB. Accepted files are read with an explicit manifest-derived byte ceiling while retaining the existing descriptor/path revision checks, so provenance cannot be forced into an unbounded source-content read.

When a supplied fan curve and operating point are available, the application builds a lightweight plot model and renders it with Tk canvas primitives. Fan/system plots reuse backend-computed system-pressure samples, label the two series, and do not reimplement system-curve equations in the GUI.

## Validation and automated smoke

Regression coverage includes end-to-end execution of every workflow exposed by the application catalog, structural registry integrity plus binding resolution, strict result serialization, relative-file adapters, project round-trip/migration/rejection cases, non-finite JSON rejection, unsaved-editor preservation and dirty-state visibility, per-analysis result restoration, active-run selection guards, unit/path flattening, headless `--check`, and execution of the active demonstration analysis.

CI retains all v0.91-v0.95 provenance/replay compatibility gates and runs the complete suite on Python 3.11/3.12/3.13. Every matrix job also builds a wheel, installs it into a clean virtual environment, validates `cleanroomx-gui --check`, and verifies the packaged demonstration resources. On Python 3.13 CI launches the real Tk GUI from that installed wheel with `--demo --smoke`, executes the active demonstration analysis, updates the UI, and exits successfully.

## Engineering boundary

The desktop application does not change CleanroomX acceptance semantics or convert screening calculations into certification evidence. CleanroomX does not by itself establish ISO cleanroom certification, CFD validation, commissioning or TAB acceptance, manufacturer approval, stall/surge safety, physical uncertainty or statistical confidence, or regulatory compliance. Source data, assumptions, boundary conditions, and applicable engineering standards remain the operator's responsibility.

## Release 2 desktop workflows

The Release 2 integration adds durable project-state and evidence workflows around the existing engineering backends:

- **Project-wide Undo/Redo** uses one bounded transaction history across project fields, analysis edits, and spatial edits. Persistent run-history evidence and the current camera/view are not rewound as design edits.
- **Saved revisions** preserve validated prior project bytes before guarded overwrites and restore only to a separate destination, keeping the currently opened project binding explicit. Revision envelopes are bounded and read through the canonical strict-JSON file boundary, so duplicate keys, non-finite values, invalid UTF-8, live-path replacement/disappearance, and revision changes during ingestion fail closed.
- **Recovery integrity** verifies current recovery artifacts with SHA-256 evidence before they are offered for restoration. Legacy v1 recovery artifacts remain readable but are labeled unverified.
- **Run history** records accepted completed runs as a bounded integrity-checked audit ledger tied to the exact analysis input and execution provenance.
- **Portable HTML reports** export the current fresh completed run as a self-contained verified engineering report. See [Portable Engineering HTML Report](PORTABLE_ENGINEERING_REPORT.md).
- **Portable project bundles** collect a project and referenced external dependencies into an integrity-checked handoff artifact. See [Project Bundles](PROJECT_BUNDLES.md).
- **Analysis plugins** use the versioned plugin API and are isolated from built-in registry keys. See [Plugins](PLUGINS.md).

Stale cached results are rejected when the active analysis input or recorded external dependency revision no longer matches the completed run.


## Project requirements traceability review

Use **Verify → Requirements Traceability...** to inspect the project-owned
requirements registry and persisted requirement-to-analysis evidence mappings
without opening the raw project JSON.

The dialog is read-only and is built from the canonical Release 3 parsers. Before
displaying mappings, it reuses the canonical cross-project mapping validation
against the current analysis collection. It shows:

- requirements and mappings SHA-256 revision identities;
- requirement-set, requirement, mapping, active-mapping, and actively mapped
  requirement counts;
- requirement lifecycle status, applicability, entity scope, and explicit
  acceptance criteria;
- mapping lifecycle status, subject reference, resolved analysis identity,
  engineering property name, and exact result path;
- complete normalized requirement or mapping JSON for the selected row.

Disabled or superseded mappings may intentionally retain historical requirement
or analysis references. The dialog labels unresolved retained references as
historical context and does not silently rebind them. A retained analysis ID is
only treated as resolved when the current analysis also matches the mapping's
recorded analysis kind; an ID reused for a different analysis kind remains
historical context.

This interface does not edit requirements or mappings, infer standards limits,
convert units, run comparisons, or issue verification verdicts. Project
requirements verification remains under the canonical Release 3 workflow and
verification engine.
