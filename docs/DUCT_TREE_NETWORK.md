# Rooted duct-tree airflow aggregation

CleanroomX v0.8 adds deterministic branch-flow aggregation for a **rooted, acyclic supply duct tree** with fixed terminal airflow demands.

This extends the v0.6 path-based pressure-loss model without claiming to solve pressure-driven flow distribution.

## Engineering basis

ASHRAE Handbook—Fundamentals, Chapter 21, *Duct Design*, treats duct-system frictional and dynamic resistance, main/branch sizing, balancing, and air distribution as core duct-design concerns. CleanroomX uses the existing v0.6 Darcy-Weisbach section pressure-loss model and adds mass-conserving airflow aggregation through a tree.

Authoritative references:

- 2025 ASHRAE Handbook—Fundamentals, Chapter 21, Duct Design:
  https://www.ashrae.org/technical-resources/ashrae-handbook
- ASHRAE Duct Fitting Database:
  https://www.ashrae.org/technical-resources/bookstore/duct-fitting-database

CleanroomX does not reproduce proprietary fitting tables or infer fitting coefficients.

## Inputs

A `duct_tree_network` contains:

- one `root_node`, normally the supply source or AHU discharge;
- directed duct sections from an upstream node to a downstream node;
- fixed terminal airflow demands.

Each tree section contains the same explicit pressure-loss inputs used by the v0.6 duct model:

- length;
- Darcy friction factor;
- air density;
- local loss coefficient;
- circular diameter, or rectangular width and height.

Section airflow is **not** entered. It is calculated from downstream terminal demand.

## Topology rules

The network must be a rooted tree:

- the root cannot have an incoming section;
- every other connected node has one incoming section at most;
- duplicate directed edges are rejected;
- directed cycles are rejected;
- every node must be reachable from the root;
- every leaf must have a positive terminal demand;
- terminal-demand node names must be unique and known to the tree.

A terminal demand may also be attached to an internal node. In that case, the incoming flow serves both the local demand and all downstream child branches.

## Flow aggregation

For a node `n`:

    subtree_flow(n) =
        terminal_demand(n)
        + sum(subtree_flow(child))

The airflow in the section entering a child node is the child's subtree flow.

At each node, CleanroomX reports the mass-balance residual:

    residual = incoming_or_source - outgoing - local_terminal_demand

For a valid deterministic aggregation, the residual is zero apart from numerical rounding.

## Pressure loss and critical terminal path

After branch airflows are calculated, every tree section is evaluated with the existing v0.6 duct-section model:

    delta_p = f * (L / D_h) * (rho V^2 / 2)
              + K * (rho V^2 / 2)

CleanroomX then traces the unique route from the root to each terminal-demand node, sums section pressure losses, and reports the terminal path with the greatest calculated pressure drop.

When a tree network is used inside an HVAC project:

- total terminal demand must match total governing HVAC supply airflow;
- the tree critical-path pressure drop becomes the duct component of preliminary supply-fan static pressure;
- the result records `computed_duct_tree_network` as the duct-pressure source.

## Boundaries

The v0.8 model uses **fixed terminal demands**. It does not solve:

- pressure-dependent branch flow distribution;
- balancing-damper positions;
- fan/system operating point;
- looped or multiply connected duct networks;
- duct leakage;
- controls or VAV response;
- system effect;
- acoustics;
- automatic friction-factor or fitting-coefficient selection.

Use the applicable project specifications, licensed standards/databases, manufacturer data, commissioning requirements, and qualified HVAC engineering review for final design.
