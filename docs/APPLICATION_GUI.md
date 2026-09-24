# CleanroomX Desktop Application

CleanroomX v0.97 provides a Tkinter desktop application over the same parsers, solvers, uncertainty engines, consistency checks, and report generators used by the command-line workflows. The GUI is an application shell over the validated backend; it does not duplicate or replace the engineering calculation implementations.

## Install and launch

Install the package in editable development mode:

```bash
python -m pip install -e .[dev]
```

Launch a new project:

```bash
cleanroomx-gui
```

Open the bundled demonstration project:

```bash
cleanroomx-gui examples/gui_demo.cleanroomx.json
```

Check the application layer without opening a window. This validates the desktop registry, including every configured parser/runner/reporter import and the custom consistency/dossier adapter contracts:

```bash
cleanroomx-gui --check
```

For CI or Linux automation with a virtual display:

```bash
xvfb-run -a cleanroomx-gui examples/gui_demo.cleanroomx.json --smoke
```

## Project format

Desktop projects use the `cleanroomx.project` JSON schema. Schema version 1 stores project metadata, an ordered list of analyses, and an optional active analysis identifier. Each analysis stores a stable id, display name, backend analysis kind, and backend input JSON.

Project saves are validated before writing and use an atomic temporary-file replacement. The loader rejects unsupported future schema versions, duplicate analysis ids, invalid active-analysis references, malformed JSON, and non-finite JSON constants such as `NaN` or `Infinity`. Supported legacy single-analysis shapes are migrated into the current document model on load.

## Operator workflow

1. Create a new project or open an existing `.cleanroomx.json` project.
2. Add an analysis from the application catalog, or select an existing analysis.
3. Edit or import the analysis input JSON. The editor accepts strict JSON objects only; non-finite constants such as `NaN` and `Infinity` are rejected.
4. Use **Validate** to run the real backend parser/validation path.
5. Use **Run** to execute the real backend workflow in a worker thread while keeping the UI responsive.
6. Inspect normalized JSON results, diagnostics/provenance evidence, Markdown reporting, and available plots.
7. Export result JSON or report Markdown and save the project.

The **Abandon** action invalidates the UI generation token so a completed worker result is ignored; Python threads are not force-terminated. While an analysis is active, CleanroomX prevents analysis mutation/switching and temporarily disables input editing so the displayed result cannot be associated with a different or modified input snapshot. The status line explicitly reports abandonment behavior.

Removing an analysis also clears any retained result owned by that analysis, preventing stale result/report export after deletion.

## Supported workflows

The application catalog is built from the shared backend registry and includes room/project verification, HVAC analysis, recovery qualification, room/qualification/thermal/psychrometric uncertainty, parallel/loop/variable-friction networks, fan operating-point and speed studies, fan-network integrations, fan/loop uncertainty, nonlinear fan/variable-friction loop analysis and uncertainty, damper studies, cross-module consistency, and engineering dossiers.

Consistency and dossier workflows resolve relative file references against the saved project directory. Save the GUI project before running those workflows when their inputs use relative paths.

## Results and plots

All backend outputs are normalized to strict JSON with non-finite values rejected. The result tab shows complete normalized JSON. The diagnostics tab extracts nested audit, integrity, trace, provenance, convergence, residual, tolerance, iteration, and coverage evidence. The report tab shows the backend Markdown reporter when one exists, otherwise a deterministic JSON-backed fallback report.

When a supplied fan curve and operating point are available, the application builds a lightweight plot model and renders it with Tk canvas primitives, avoiding a GUI-only numerical dependency.

## Validation and automated smoke

Regression coverage includes end-to-end execution of every workflow exposed by the application catalog, strict result serialization, relative-file adapters, project round-trip/migration/rejection cases, non-finite JSON rejection, unsaved-editor preservation, active-run selection guards, unit/path flattening, headless registry-integrity `--check`, and execution of the active demonstration analysis.

CI retains all v0.91-v0.95 provenance/replay compatibility gates, runs the dedicated v0.97 application/workflow/lifecycle gate and the complete suite on Python 3.11/3.12/3.13, and on Python 3.13 additionally installs a virtual display, runs the installed registry-integrity `cleanroomx-gui --check` entry point, launches the real Tk GUI under Xvfb, loads the demonstration project, executes its active analysis, updates the UI, and exits successfully.

## Engineering boundary

The desktop application does not change CleanroomX acceptance semantics or convert screening calculations into certification evidence. CleanroomX does not by itself establish ISO cleanroom certification, CFD validation, commissioning or TAB acceptance, manufacturer approval, stall/surge safety, physical uncertainty or statistical confidence, or regulatory compliance. Source data, assumptions, boundary conditions, and applicable engineering standards remain the operator's responsibility.
