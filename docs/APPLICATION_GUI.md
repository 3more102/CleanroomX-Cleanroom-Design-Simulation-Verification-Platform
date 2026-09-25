# CleanroomX Desktop Application

CleanroomX v0.100 provides a Tkinter desktop application over the same parsers, solvers, uncertainty engines, consistency checks, and report generators used by the command-line workflows. The GUI is an application shell over the validated backend; it does not duplicate or replace the engineering calculation implementations.

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

Project saves are validated before writing and use an atomic temporary-file replacement. The loader rejects unsupported future schema versions, duplicate analysis ids, invalid active-analysis references, malformed JSON, and non-finite JSON constants such as `NaN` or `Infinity`. Supported legacy single-analysis shapes are migrated into the current document model on load.

## Recovery autosave

The desktop application maintains crash-recovery autosaves separately from explicit project files. By default, a dirty project is sampled every 60 seconds; use `--autosave-interval-seconds N` to change the interval or `0` to disable recovery autosave. The right side of the status bar reports whether autosave is ready, saving, saved, clean, or failed.

Autosave never writes to the open `.cleanroomx.json` path. It writes a versioned `cleanroomx.autosave` recovery envelope in the per-user recovery directory using the same atomic-write primitive as project persistence. Writes run on a single background worker, identical snapshots are suppressed, newer pending edits are coalesced, and history is bounded per project identity.

Each artifact contains the recoverable project snapshot, the active raw editor draft, application version, recovery timestamp, project identity, and a source-file fingerprint containing path, size, modification time, and SHA-256. A malformed JSON editor draft is preserved as raw text without being promoted into the authoritative project model. The recovery scanner reports malformed artifacts explicitly and classifies the source project as unchanged, changed, missing, or newer. This foundation never automatically overwrites a newer project file.

Current-session recovery artifacts are invalidated after an explicit save or an explicit discard. Recovery files from older sessions are not silently deleted by merely opening or saving the same project; the source comparison evidence remains available for the dedicated startup recovery workflow.

## Operator workflow

1. Create a new project or open an existing `.cleanroomx.json` project.
2. Add an analysis from the application catalog, or select an existing analysis.
3. Edit or import the analysis input JSON. The editor accepts strict JSON objects only; non-finite constants such as `NaN` and `Infinity` are rejected.
4. Use **Validate** to run the real backend parser/validation path.
5. Use **Run** to execute the real backend workflow in a worker thread while keeping the UI responsive.
6. Inspect normalized JSON results, diagnostics/provenance evidence, Markdown reporting, and available plots.
7. Export input/result JSON, complete run-bundle JSON, or report Markdown and save the project. Writes are atomic and filesystem errors are surfaced in the GUI.

The **Abandon** action suppresses the pending result but does not force-terminate Python threads. The application keeps the run exclusive and input locked until that worker actually exits, so abandoning a long computation cannot create overlapping backend runs. The status line reports both the waiting and worker-finished states.

Removing an analysis also clears any retained result owned by that analysis, preventing stale result/report export after deletion.

## Supported workflows

The application catalog is built from the shared backend registry and includes room/project verification, HVAC analysis, recovery qualification, room/qualification/thermal/psychrometric uncertainty, parallel/loop/variable-friction networks, fan operating-point and speed studies, fan-network integrations, fan/loop uncertainty, nonlinear fan/variable-friction loop analysis and uncertainty, damper studies, cross-module consistency, and engineering dossiers.

Consistency and dossier workflows resolve relative file references against project path context. Imported JSON is rebased from its source directory, and **Save Project As** rebases relative references when the destination directory changes. Absolute-only dossier inputs can run before the project is saved; relative references still require an explicit base directory. The installed `--demo` project ships its referenced files beside the project file.

## Spatial design workspace

The main notebook now includes **Design 2D + 3D**, a synchronized cleanroom layout workspace backed by project metadata. It is intentionally separate from the engineering solver implementations: spatial edits do not silently change analysis inputs.

The 2D view supports room creation, selection, drag movement with metric grid snapping, property editing and resizing, deletion, zoom, pan, fit-to-view, coordinate feedback, and placement of doors, FFUs, supply points, returns, exhausts, equipment, and sensors. Spatial model edits have bounded transactional **Undo/Redo**: add, delete, property changes, and a full drag gesture are each one history operation; redo is invalidated by a new divergent edit, and undo/redo restores selection without rewinding the current camera/view state. Toolbar buttons expose the feature, with Ctrl+Z, Ctrl+Y, and Ctrl+Shift+Z available while a spatial canvas has focus. When room pressure is present in a verification input, the layout visualizes only that supplied pressure data; it does not invent pressure values.

The 3D view is generated from the same canonical spatial model as the 2D layout. Room dimensions, labels, selection, and devices therefore stay synchronized. The view supports azimuth rotation, elevation adjustment, zoom, pan, reset, and fit behavior without adding a third-party rendering dependency.

For room-verification and multi-room project-verification analyses, **Sync dimensions to active analysis** explicitly copies room dimensions (and an existing observed-pressure field when present) from the spatial model into the analysis JSON. Other engineering fields such as airflow, ACH requirements, particle requirements, and pressure-cascade criteria are preserved. Results for a synchronized analysis are invalidated and must be validated/run again.

Existing projects remain schema-version-1 compatible because the spatial document is stored under the existing project metadata block. If no spatial metadata exists, CleanroomX can seed a layout from real room geometry found in a verification analysis. Projects with no such geometry remain empty until the operator adds rooms.

## Results and plots

All backend outputs are normalized to strict JSON with non-finite values rejected. Successful runs record canonical application-input SHA-256 provenance; consistency/dossier runs also capture before/after SHA-256 and byte-size evidence for external dependencies. Diagnostics exposes the evidence and **Export Run Bundle JSON** preserves it with result, report, diagnostics, and plot data.

When a supplied fan curve and operating point are available, the application builds a lightweight plot model and renders it with Tk canvas primitives. Fan/system plots reuse backend-computed system-pressure samples, label the two series, and do not reimplement system-curve equations in the GUI.

## Validation and automated smoke

Regression coverage includes end-to-end execution of every workflow exposed by the application catalog, structural registry integrity plus binding resolution, strict result serialization, relative-file adapters, project round-trip/migration/rejection cases, non-finite JSON rejection, unsaved-editor preservation and dirty-state visibility, per-analysis result restoration, active-run selection guards, unit/path flattening, headless `--check`, and execution of the active demonstration analysis.

CI retains all v0.91-v0.95 provenance/replay compatibility gates and runs the complete suite on Python 3.11/3.12/3.13. Every matrix job also builds a wheel, installs it into a clean virtual environment, validates `cleanroomx-gui --check`, and verifies the packaged demonstration resources. On Python 3.13 CI launches the real Tk GUI from that installed wheel with `--demo --smoke`, executes the active demonstration analysis, updates the UI, and exits successfully.

## Engineering boundary

The desktop application does not change CleanroomX acceptance semantics or convert screening calculations into certification evidence. CleanroomX does not by itself establish ISO cleanroom certification, CFD validation, commissioning or TAB acceptance, manufacturer approval, stall/surge safety, physical uncertainty or statistical confidence, or regulatory compliance. Source data, assumptions, boundary conditions, and applicable engineering standards remain the operator's responsibility.
