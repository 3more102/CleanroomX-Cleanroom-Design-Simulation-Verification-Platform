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

The headless check validates the application registry as an executable contract before reporting readiness. It rejects duplicate analysis keys, missing parser/runner bindings on ordinary analyses, accidental parser/runner bindings on custom `consistency`/`dossier` adapters, unresolved/non-callable targets, and returns auditable registry metadata alongside the package version and catalog size.

For CI or Linux automation with a virtual display:

```bash
xvfb-run -a cleanroomx-gui --demo --smoke
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
7. Export result JSON, a complete run-bundle JSON (including diagnostics/provenance), or report Markdown and save the project.

The **Abandon** action suppresses the pending result but does not force-terminate Python threads. The application keeps the run exclusive and input locked until that worker actually exits, so abandoning a long computation cannot create overlapping backend runs. The status line reports both the waiting and worker-finished states.

Removing an analysis also clears any retained result owned by that analysis, preventing stale result/report export after deletion.

## Supported workflows

The application catalog is built from the shared backend registry and includes room/project verification, HVAC analysis, recovery qualification, room/qualification/thermal/psychrometric uncertainty, parallel/loop/variable-friction networks, fan operating-point and speed studies, fan-network integrations, fan/loop uncertainty, nonlinear fan/variable-friction loop analysis and uncertainty, damper studies, cross-module consistency, and engineering dossiers.

Consistency and dossier workflows resolve relative file references against the saved project directory. Relative references require a saved project/base directory, while dossiers containing only absolute references can run before the project is saved. Importing analysis JSON rebases declared file references into the current project context, and **Save Project As** rewrites relative references so they keep identifying the same files after relocation. Cached results are cleared when the base directory changes. The installed `--demo` project remains self-contained after wheel installation.

## Results and plots

All backend outputs are normalized to strict JSON with non-finite values rejected. Every successful application run records canonical input SHA-256 provenance; file-backed consistency/dossier runs also record dependency SHA-256 and byte-size evidence before and after execution. The result tab shows complete normalized JSON, Diagnostics includes the application-execution provenance, **Export Run Bundle JSON** preserves the complete run object, and the report tab shows the backend Markdown reporter when one exists, otherwise a deterministic JSON-backed fallback report.

When a supplied fan curve and operating point are available, the application builds a lightweight plot model and renders it with Tk canvas primitives, avoiding a GUI-only numerical dependency. Backend-computed system-pressure evidence is drawn as a distinct labeled system-curve series when available.

## Validation and automated smoke

Regression coverage includes end-to-end execution of every workflow exposed by the application catalog, catalog/mapping parity and binding resolution, canonical input/dependency provenance, absolute/relative dossier path rules, import/Save-As path rebasing, base-directory cache invalidation, abandoned-worker exclusivity, atomic writes and export failures, run-bundle export, project migration/rejection cases, strict result serialization, headless `--check`, and packaged-demo execution.

CI retains all v0.91-v0.95 provenance/replay compatibility gates, runs a focused v0.100 application/project/GUI gate and the complete suite on Python 3.11/3.12/3.13, then builds and installs a clean wheel in every matrix job. The installed `cleanroomx-gui --check` and packaged resources are validated, and Python 3.13 launches the installed real Tk GUI with `--demo --smoke` under Xvfb.

## Engineering boundary

The desktop application does not change CleanroomX acceptance semantics or convert screening calculations into certification evidence. CleanroomX does not by itself establish ISO cleanroom certification, CFD validation, commissioning or TAB acceptance, manufacturer approval, stall/surge safety, physical uncertainty or statistical confidence, or regulatory compliance. Source data, assumptions, boundary conditions, and applicable engineering standards remain the operator's responsibility.
