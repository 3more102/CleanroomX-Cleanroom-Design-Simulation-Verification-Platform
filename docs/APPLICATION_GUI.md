# CleanroomX Desktop Application

CleanroomX v0.100.0 provides a Tkinter desktop application over the same parsers, solvers, uncertainty engines, consistency checks, and report generators used by the command-line workflows. The GUI is an application shell over the validated backend; it does not duplicate or replace the engineering calculation implementations.

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

The headless check validates the application registry as an executable contract before reporting readiness. It rejects duplicate analysis keys, missing parser/runner bindings on ordinary analyses, accidental parser/runner bindings on custom `consistency`/`dossier` adapters, unresolved/non-callable targets, and returns auditable registry metadata alongside the package version and catalog size.

For CI or Linux automation with a virtual display:

```bash
xvfb-run -a cleanroomx-gui --demo --smoke
```

## Project format

Desktop projects use the `cleanroomx.project` JSON schema. Schema version 1 stores project metadata, an ordered list of analyses, and an optional active analysis identifier. Each analysis stores a stable id, display name, backend analysis kind, and backend input JSON.

Project saves are validated before writing and use a same-directory atomic temporary-file replacement. GUI input/result/run-bundle/report exports use the same atomic writer and surface filesystem failures to the operator. The loader rejects unsupported future schema versions, duplicate analysis ids, invalid active-analysis references, malformed JSON, and non-finite JSON constants such as `NaN` or `Infinity`. Supported legacy single-analysis shapes are migrated into the current document model on load.

## Operator workflow

1. Create a new project or open an existing `.cleanroomx.json` project.
2. Add an analysis from the application catalog, or select an existing analysis.
3. Edit or import the analysis input JSON. The editor accepts strict JSON objects only; non-finite constants such as `NaN` and `Infinity` are rejected.
4. Use **Validate** to run the real backend parser/validation path.
5. Use **Run** to execute the real backend workflow in a worker thread while keeping the UI responsive.
6. Inspect normalized JSON results, diagnostics/provenance evidence, Markdown reporting, and available plots.
7. Export result JSON, a complete run-bundle JSON with execution provenance, or report Markdown, then save the project.

The **Abandon** action suppresses the pending result but does not force-terminate Python threads. The application keeps the run exclusive and input locked until that worker actually exits, so abandoning a long computation cannot create overlapping backend runs. The status line reports both the waiting and worker-finished states.

Removing an analysis also clears any retained result owned by that analysis, preventing stale result/report export after deletion.

## Supported workflows

The application catalog is built from the shared backend registry and includes room/project verification, HVAC analysis, recovery qualification, room/qualification/thermal/psychrometric uncertainty, parallel/loop/variable-friction networks, fan operating-point and speed studies, fan-network integrations, fan/loop uncertainty, nonlinear fan/variable-friction loop analysis and uncertainty, damper studies, cross-module consistency, and engineering dossiers.

Consistency and dossier workflows resolve relative file references against the saved project directory. Importing analysis JSON and **Save Project As** rebase supported consistency/dossier references so they continue to identify the same files when directory context changes; changing that context clears cached run results. Unsaved dossier projects can execute only when every referenced file is absolute. The installed `--demo` project ships its referenced consistency/dossier inputs beside the project file, so the demonstration remains self-contained after wheel installation.

## Results and plots

All backend outputs are normalized to strict JSON with non-finite values rejected. The result tab shows complete normalized JSON. The diagnostics tab extracts nested audit, integrity, trace, provenance, convergence, residual, tolerance, iteration, and coverage evidence. The report tab shows the backend Markdown reporter when one exists, otherwise a deterministic JSON-backed fallback report.

When a supplied fan curve and operating point are available, the application builds a lightweight plot model from backend evidence. Where available, the model includes both supplied fan-curve and backend-computed system-curve series plus the operating-point marker, rendered with Tk canvas primitives without a GUI-only numerical dependency.

Each application run also records canonical input SHA-256 identity and before/after identity/size evidence for supported external file dependencies. This software-provenance evidence is shown in Diagnostics and is included in **Export Run Bundle JSON**.

## Validation and automated smoke

Regression coverage includes end-to-end execution of every workflow exposed by the application catalog, structural registry integrity plus binding resolution, strict result serialization, relative-file adapters, project round-trip/migration/rejection cases, non-finite JSON rejection, unsaved-editor preservation and dirty-state visibility, per-analysis result restoration, active-run selection guards, unit/path flattening, headless `--check`, and execution of the active demonstration analysis.

CI retains all v0.91-v0.95 provenance/replay compatibility gates and runs the complete suite on Python 3.11/3.12/3.13. Every matrix job also builds a wheel, installs it into a clean virtual environment, validates `cleanroomx-gui --check`, and verifies the packaged demonstration resources. On Python 3.13 CI launches the real Tk GUI from that installed wheel with `--demo --smoke`, executes the active demonstration analysis, updates the UI, and exits successfully.

## Engineering boundary

The desktop application does not change CleanroomX acceptance semantics or convert screening calculations into certification evidence. CleanroomX does not by itself establish ISO cleanroom certification, CFD validation, commissioning or TAB acceptance, manufacturer approval, stall/surge safety, physical uncertainty or statistical confidence, or regulatory compliance. Source data, assumptions, boundary conditions, and applicable engineering standards remain the operator's responsibility.
