# Branch-flow supply-tree model

CleanroomX v0.8 extends the v0.6 path pressure-loss model with automatic airflow propagation through a directed supply tree.

## What is solved

The user defines:

- one source node;
- directed duct branches with geometry, air density, local loss coefficient, and either an explicit Darcy friction factor or automatic-friction roughness/viscosity inputs;
- one fixed airflow demand at every leaf terminal.

For a branch feeding a downstream subtree, CleanroomX applies steady-state mass continuity:

    branch airflow = sum of all downstream terminal demands

The source airflow is therefore:

    source airflow = sum of all terminal demands

After branch flows are known, each branch is evaluated with the Darcy-Weisbach plus local-K pressure-loss model. When v0.19 automatic friction is selected, Reynolds number and the Darcy factor are resolved at that branch's solved airflow before its pressure loss is calculated. Pressure loss is accumulated from the source to every terminal, and the terminal path with the largest loss is reported as the critical path.

## Topology validation

The v0.8 solver intentionally accepts a directed tree only. It rejects:

- multiple incoming branches to one node;
- an incoming branch to the source;
- unreachable/disconnected branch nodes;
- terminal demands placed on non-leaf nodes;
- leaf nodes without a terminal demand;
- duplicate branch names or duplicate terminal demands.

This keeps the continuity solution deterministic and auditable.

## HVAC integration

An HVAC project may configure either:

- the v0.6 explicit `duct_network` path-comparison model; or
- the v0.8 `branch_flow_network` supply-tree model.

They are mutually exclusive. For a branch-flow network, the sum of terminal demands must match the HVAC project's total governing supply airflow within a small numerical tolerance before its critical-path pressure loss can be used for supply-fan duty.

## Engineering boundary

This is not a general nonlinear airflow-network solver. Terminal demands are fixed inputs; CleanroomX does not solve pressure-driven terminal flows, looped networks, parallel feeds, damper positions, fan curves, leakage, system effect, or controls. Local loss coefficients remain explicit engineering inputs. Friction factors may remain explicit or, in v0.19, be resolved from explicit roughness and kinematic viscosity after branch airflow is known. This still is not iterative pressure-driven network balancing.

Use current project specifications, applicable licensed standards, manufacturer data, and qualified HVAC/cleanroom engineering review for real designs.
