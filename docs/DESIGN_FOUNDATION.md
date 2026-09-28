# CleanroomX Design Foundation

CleanroomX Phase 1 now has three complementary engineering foundations:

1. the existing [room pressure / leakage network](PRESSURE_NETWORK.md);
2. a traceable design-requirements engine;
3. a preliminary cleanroom air-system designer.

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

## Pressure-network integration

The pressure/leakage network remains the stronger implementation already present on `main`, with strict input parsing, CLI support, fixed-pressure boundaries, explicit power-law/orifice paths, damped-Newton continuity solving, target checks, residual/convergence evidence, and its own documentation.

The design-requirements and air-system workflows are intentionally separate services so future phases can connect them through explicit mappings rather than duplicating pressure physics.

## Engineering boundary

These workflows are preliminary engineering design/screening tools. They do not infer standards requirements, construction leakage, manufacturer performance, CFD results, certification, regulatory approval, or commissioning/TAB acceptance.
