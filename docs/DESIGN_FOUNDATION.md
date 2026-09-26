# CleanroomX Design Foundation

CleanroomX Phase 1 now has three complementary engineering foundations plus an explicit cross-workflow consistency layer:

1. the existing [room pressure / leakage network](PRESSURE_NETWORK.md);
2. a traceable design-requirements engine;
3. a preliminary cleanroom air-system designer;
4. a read-only design-requirements ↔ air-system consistency analysis.

They are registered through the same application parser/runner/reporter boundary as existing analyses, so the desktop application, saved projects, deterministic project batch execution, run provenance, and reporting can reuse the engineering services without a second execution stack.

## Design requirements

The `design_requirements` workflow converts explicit room requirements and explicitly selected project/reference profiles into structured design targets.

For every derived target it retains:

- value and unit;
- source;
- equation;
- assumptions;
- status;
- warnings;
- provenance.

Room inputs explicitly override a selected profile. Missing requirements remain unchecked or warning state instead of being silently invented. Reference profiles are project data; they are not hard-coded regulatory requirements.

Current derived evidence includes room area, volume, ACH-based airflow target, and explicitly entered sensible-load totals, while retaining room classification, intended process, occupancy, temperature/RH ranges, pressure target, recovery target, filtration requirement, contamination assumptions, supply/return strategy, and operating mode.

## Air-system design

The `air_system_design` workflow evaluates explicit preliminary airflow drivers:

- minimum ACH;
- sensible-load airflow using disclosed air properties and room/supply temperatures;
- minimum outdoor airflow.

The largest evaluated driver becomes the governing preliminary supply airflow. The result then exposes a proposed return airflow, exhaust/transfer balance, minimum-surplus evidence, preliminary makeup airflow, and capacity-based counts for user-supplied FFU/filter units and supply/return/exhaust terminals.

Supported strategy labels include ceiling-supply/low-return, FFU ceiling, mixed return, wall return, positive-pressure suite, negative-pressure containment, unidirectional concept, and turbulent/mixing concept. Strategy labels do not inject hidden airflow requirements.

## Design consistency

The `design_consistency` workflow composes the existing design-requirements and air-system services; it does not create another room model or reimplement either calculation engine.

It compares only quantities represented explicitly on both sides:

- room-set identity by stable room name;
- room length, width, and height;
- configured minimum ACH;
- ACH-derived supply airflow;
- explicitly entered sensible load;
- air-system room temperature against the configured requirement range.

Every numeric comparison uses a caller-supplied absolute tolerance (default `0`), and each finding retains expected value, actual value, delta, unit, tolerance, status, and applicable requirement provenance. Missing requirement evidence remains `not_checked`; a configured requirement missing from the air-system input fails the corresponding comparison. Aggregate status uses the same `pass` / `fail` / `pass_with_unchecked` / `not_checked` semantics as CleanroomX verification.

Relative humidity, pressure targets, recovery targets, filtration text, contamination assumptions, operating mode, and free-text supply/return strategy are deliberately not inferred across workflows. The result lists those boundaries explicitly so a consistency pass cannot be mistaken for a pressure-network, filtration, contamination-control, CFD, commissioning/TAB, certification, or regulatory verdict.

## Pressure-network integration

The pressure/leakage network remains the stronger implementation already present on `main`, with strict input parsing, CLI support, fixed-pressure boundaries, explicit power-law/orifice paths, damped-Newton continuity solving, target checks, residual/convergence evidence, and its own documentation.

The design-requirements and air-system workflows are intentionally separate services so future phases can connect them through explicit mappings rather than duplicating pressure physics.

## Engineering boundary

These workflows are preliminary engineering design/screening tools. They do not infer standards requirements, construction leakage, manufacturer performance, CFD results, certification, regulatory approval, or commissioning/TAB acceptance.
