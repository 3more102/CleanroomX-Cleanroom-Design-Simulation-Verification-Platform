# Pressure Design Consistency

The `pressure_design_consistency` workflow is a read-only bridge between the existing design-requirements engine and the existing room pressure-network solver.

It does not add a new pressure equation or infer standards requirements. It solves the supplied canonical pressure network and compares a room's configured `pressure_target_pa` only to an explicitly mapped node-to-reference pressure difference.

## Input contract

A study contains:

- `requirements`: an ordinary `design_requirements` object;
- `pressure_network`: an ordinary room pressure-network object;
- `mappings`: explicit room → network node/reference-node mappings;
- `pressure_abs_tolerance_pa`: an explicit absolute comparison tolerance;
- `require_all_configured_targets_mapped`: whether a configured room target without a mapping is a failure. The default is `true`.

Example mapping:

```json
{
  "room": "Process",
  "node": "Process",
  "reference_node": "Corridor"
}
```

For that mapping, CleanroomX evaluates:

`observed_delta_pa = pressure(node) - pressure(reference_node)`

and compares it with the configured room `pressure_target_pa`.

The sign is preserved. A negative-pressure room can therefore use a negative target when the explicit node/reference ordering is appropriate.

## Result semantics

Each requirements room receives one finding:

- `pass`: a configured target has an explicit mapping and the solved difference is within tolerance;
- `fail`: a configured target is outside tolerance, or a required mapping is missing;
- `not_checked`: no target is configured, or mapping completeness was explicitly disabled for an unmapped configured target.

The result preserves expected value, actual solved pressure difference, delta, tolerance, unit, mapping, and requirements provenance.

The pressure network's own configured target checks remain separate evidence. Their status and target summary are surfaced under `source_analyses.pressure_network`, but they are not silently converted into design-requirement mappings.

## Application integration

The workflow is registered in the shared CleanroomX application catalog as `pressure_design_consistency`. It is therefore available to the desktop/project execution boundary and deterministic project batch automation without a second solver path.

A demonstration input is provided at:

```text
examples/pressure_design_consistency_demo.json
```

## Engineering boundary

This workflow does not infer a reference room, leakage coefficient, opening area, pressure target, standard limit, regulatory criterion, wind/stack effect, or transient door behavior. A complete pass establishes only consistency between supplied design pressure targets and explicitly mapped steady-state pressure-network results within the supplied tolerance. It is not cleanroom certification, commissioning/TAB acceptance, CFD validation, or regulatory approval.
