# CleanroomX Design Foundation

CleanroomX Phase 1 now has three complementary engineering foundations plus two explicit cross-workflow consistency layers:

1. the existing [room pressure / leakage network](PRESSURE_NETWORK.md);
2. a traceable design-requirements engine;
3. a preliminary cleanroom air-system designer;
4. a read-only design-requirements ↔ air-system consistency analysis;
5. a read-only design pressure-target ↔ pressure-network consistency analysis.

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
- minimum outdoor airflow;
- the room air-balance requirement needed to support configured exhaust, transfer-out, and minimum surplus after transfer-in.

The air-balance sizing requirement is

`max(0, exhaust + transfer_out + minimum_surplus - transfer_in)`.

This follows from the steady room balance

`supply + transfer_in = return + exhaust + transfer_out + surplus`

with non-negative return airflow and `surplus >= minimum_surplus`. The largest evaluated driver becomes the governing preliminary supply airflow, so a configured surplus target cannot be undercut merely by clamping return airflow to zero. Results expose the balance driver, proposed return airflow, configured minimum surplus, achieved surplus, surplus margin, exhaust/transfer evidence, preliminary makeup airflow, and capacity-based counts for user-supplied FFU/filter units and supply/return/exhaust terminals.

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

Relative humidity, pressure targets, recovery targets, filtration text, contamination assumptions, operating mode, and free-text supply/return strategy are deliberately not inferred inside this air-system consistency workflow. Pressure-target comparison is handled separately by the explicit-mapping `pressure_design_consistency` workflow described below. The result lists those boundaries explicitly so an air-system consistency pass cannot be mistaken for a pressure-network, filtration, contamination-control, CFD, commissioning/TAB, certification, or regulatory verdict.

## Pressure-network integration

The pressure/leakage network remains the stronger implementation already present on `main`, with strict input parsing, CLI support, fixed-pressure boundaries, explicit power-law/orifice paths, damped-Newton continuity solving, target checks, residual/convergence evidence, and its own documentation.

Phase 1 now adds a read-only `pressure_design_consistency` composer. It requires an explicit mapping from each compared requirements room to a pressure-network node and reference node, then compares the configured signed `pressure_target_pa` only with `pressure(node) - pressure(reference_node)` using a caller-supplied absolute tolerance. It never infers a reference room or converts the pressure network's own target definitions into requirements semantics. Missing configured mappings fail by default and can only be left unresolved by explicitly disabling complete mapping.

The design-requirements, air-system, and pressure-network workflows remain separate canonical services so composition adds traceability without duplicating pressure physics.

## Engineering boundary

These workflows are preliminary engineering design/screening tools. They do not infer standards requirements, construction leakage, manufacturer performance, CFD results, certification, regulatory approval, or commissioning/TAB acceptance.
