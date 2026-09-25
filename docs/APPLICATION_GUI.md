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

### External-change write protection

When a saved project is opened, CleanroomX records a stable content revision using the normalized path, size, modification timestamp, and SHA-256 digest. **Save Project** is an optimistic guarded write: the destination must still match the content revision that was opened or produced by the previous successful save. The guard is checked before serialization and again immediately before the atomic replace.

If another CleanroomX window or external editor changes, deletes, or replaces the project file, the save is blocked and the newer on-disk file is preserved. The application directs the operator to **Save Project As** to preserve the current window's work under another name, or to reopen the project to accept the disk version. Selecting the already-open project path through **Save Project As** does not bypass the guard. Timestamp-only metadata changes with identical file content do not create a false conflict.

For a genuinely different Save As destination, CleanroomX captures the destination revision after the file chooser returns and applies the same guarded replace, protecting against a race where another process changes or creates the target before the atomic commit.

### Saved project revisions

Before a changed guarded overwrite of an existing valid CleanroomX project, the application preserves the exact previous project bytes in a bounded sidecar revision history. Each revision records the normalized source path, byte size, SHA-256 identity, CleanroomX version, and exact UTC timestamp. Identical saves do not generate redundant revisions. Corrupted or malformed revision artifacts are reported and preserved rather than silently accepted.

After atomic replacement, CleanroomX reloads the project from disk and verifies both its stable SHA-256 content identity and parsed project model. If this verification fails, rollback to the prior bytes is attempted only while the destination can still be proven to contain CleanroomX's own attempted write. If another process changes the destination again, CleanroomX does not overwrite that external change and retains the prior saved revision as recovery evidence.

Use **File → Saved Revisions…** to browse valid prior explicit saves. **Restore as Copy…** verifies the selected revision and requires a separate destination; it never overwrites the source project. If an existing restore destination is a valid CleanroomX project, that destination is itself preserved as a revision before replacement. Restore writes are guarded against destination races and verified after commit.

## Recovery autosave

The desktop application maintains crash-recovery autosaves separately from explicit project files. Dirty edits schedule an idle-debounced recovery checkpoint after 1.5 seconds, while the 60-second periodic sampler remains a fallback for long-lived dirty sessions. Rapid edits reset the short checkpoint so typing and drag gestures coalesce instead of generating one file per event. Use `--autosave-interval-seconds N` to change the periodic fallback interval or `0` to disable recovery autosave entirely. The right side of the status bar reports whether autosave is ready, saving, saved, clean, or failed.

Autosave never writes to the open `.cleanroomx.json` path. It writes a versioned `cleanroomx.autosave` recovery envelope in the per-user recovery directory using the same atomic-write primitive as project persistence. Writes run on a single background worker, identical snapshots are suppressed, newer pending edits are coalesced, and history is bounded per project identity.

Each artifact contains the recoverable project snapshot, the active raw editor draft, application version, recovery timestamp, project identity, and a source-file fingerprint containing path, size, modification time, and SHA-256. A malformed JSON editor draft is preserved as raw text without being promoted into the authoritative project model. The recovery scanner reports malformed artifacts explicitly and classifies the source project as unchanged, changed, missing, or newer. This foundation never automatically overwrites a newer project file.

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
7. Export input/result JSON, complete run-bundle JSON, or report Markdown and save the project. Explicit project saves are externally guarded, revision-preserving, atomically replaced, and re-verified; filesystem errors are surfaced in the GUI.

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
