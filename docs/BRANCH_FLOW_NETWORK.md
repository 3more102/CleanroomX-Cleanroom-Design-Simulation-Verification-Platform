# Room-linked branch-flow supply-tree model

CleanroomX v0.8 extends the path-based duct model with automatic airflow propagation through a rooted supply tree.

## Inputs

The project defines one source node, directed duct branches, and one terminal-to-room mapping at every leaf. Branch geometry, Darcy friction factor, air density, and local loss coefficient remain explicit engineering inputs.

Terminal airflow is not duplicated in the duct input. CleanroomX takes each mapped room's already-computed governing HVAC supply airflow and uses it as the terminal demand.

## Flow solution

For every branch:

    branch airflow = sum of governing room airflows in the downstream subtree

At the source:

    source airflow = sum of all mapped room governing airflows

The solver reports continuity residuals at every node.

After flow propagation, each branch is evaluated with the existing Darcy-Weisbach plus local-K pressure-loss model. Losses are accumulated from the source to every terminal, and the largest source-to-terminal loss becomes the critical path used for preliminary fan static-pressure sizing.

## Validation

The model accepts a rooted directed tree only. It rejects multiple incoming branches, an incoming branch to the source, disconnected nodes, duplicate branch names, duplicate terminal nodes, duplicate room mappings, non-leaf terminals, leaves without terminals, and HVAC rooms that are not mapped exactly once.

## Engineering boundary

This is a fixed-demand mass-continuity solver, not a general nonlinear pressure-balancing network solver. It does not solve looped networks, parallel feeds, leakage, pressure-driven terminal flows, balancing-damper positions, fan curves, system effect, acoustic performance, or controls.

Use current project specifications, applicable licensed standards, manufacturer data, and qualified HVAC/cleanroom engineering review for real designs.
