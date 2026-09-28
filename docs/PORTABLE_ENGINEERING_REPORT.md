# Portable Engineering HTML Report

CleanroomX can export the currently selected completed analysis as one self-contained HTML engineering report from **File → Export Portable HTML Report…**.

The export is designed for review, handoff, printing, and archival without requiring CleanroomX or network access to open the document.

## Evidence included

The document contains:

- project name and description;
- stable analysis id, display name, workflow kind, and completed status;
- the canonical SHA-256 of the exact submitted analysis input;
- the exact submitted analysis input JSON;
- the normalized engineering result JSON;
- diagnostics and application execution provenance;
- the backend-generated Markdown engineering report;
- a machine-readable `cleanroomx.engineering-report` JSON payload embedded in the HTML;
- a SHA-256 digest over that canonical payload, excluding only the integrity object itself.

The embedded digest is deterministic integrity evidence. It is not a digital signature, source authentication, certification, or proof that the engineering assumptions are correct.

## Freshness and correctness boundary

HTML generation never invokes a solver and never recomputes engineering equations. Before assembling report evidence, the report builder independently applies the same canonical analysis-input identity check used by the desktop stale-result guard.

If the analysis kind or input no longer matches the completed run provenance, report generation fails and the operator must rerun the analysis. This remains true when the report builder is called directly from Python rather than through the GUI.

## Safety and portability

The report:

- contains no external scripts, stylesheets, fonts, images, or network resources;
- HTML-escapes project, analysis, Markdown, input, result, and diagnostic presentation text;
- encodes the embedded JSON so user data cannot terminate the non-executable JSON script element;
- routes project/analysis metadata and custom limitations through the shared Markdown structure-escaping boundary in the portable Markdown renderer, so embedded newlines, table delimiters, emphasis markers, and HTML remain text rather than report structure;
- validates the deterministic payload digest before rendering;
- serializes JSON with `allow_nan=False`;
- is written by the desktop through the existing atomic export path.

No project schema change is introduced. Existing `.cleanroomx.json` files, analysis APIs, solver behavior, project persistence, plugins, and prior Markdown/JSON export workflows are unchanged.

## Programmatic use

`cleanroomx.engineering_report` exposes:

- `build_engineering_report_payload(...)` — construct deterministic evidence after freshness validation;
- `verify_engineering_report_payload(payload)` — recompute and compare report-payload integrity;
- `render_engineering_report_html(payload)` — render only a valid payload;
- `engineering_report_html(...)` — freshness-check, build, verify, and render in one call.

The HTML output is deterministic for identical inputs and run evidence because no wall-clock timestamp, random identifier, local path, or external resource is inserted.
