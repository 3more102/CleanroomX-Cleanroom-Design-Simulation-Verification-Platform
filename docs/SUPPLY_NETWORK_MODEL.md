# Supply branch-flow network model

CleanroomX v0.7 adds deterministic supply-airflow propagation through a rooted branch network.

## Purpose

The model removes repeated manual branch-flow arithmetic. Each HVAC room is mapped to one supply node. CleanroomX first calculates the room's governing supply airflow, then sums downstream demand toward the configured source node.

A supply node may also include explicit fixed auxiliary airflow for loads that are not represented by an HVAC room, such as a separately specified terminal or process-air allowance.

For each branch:

    branch airflow = total demand downstream of that branch

At the source:

    source airflow = sum(room governing airflow) + sum(fixed auxiliary airflow)

## Topology rules

The supply network is intentionally restricted to a rooted tree:

- the source node must exist and cannot have an incoming branch;
- every other node must have exactly one incoming branch;
- node and branch names must be unique;
- every node must be reachable from the source;
- each HVAC room may be referenced by only one supply node;
- when a supply network is used in an HVAC project, every HVAC room must be mapped.

These constraints make the aggregation deterministic and auditable.

## Duct integration

A duct section may optionally set:

    "flow_source_branch": "Main trunk"

When the HVAC project also contains a supply network, the solved airflow for that named branch overrides the section's configured `airflow_m3_h` during pressure-loss analysis.

The configured airflow remains required as an explicit standalone/fallback value so the duct network can still be analyzed without a supply network.

## Fan integration

When a supply network is present, preliminary fan airflow uses the solved source airflow rather than only the sum of room governing flows. This allows explicit fixed auxiliary airflow to be included in fan duty.

## Engineering boundary

This is a demand-aggregation solver, not a pressure-balanced airflow-network solver. It does not infer flow from branch resistance, solve dampers, model leakage, apply diversity automatically, determine fan operating point, or simulate controls.

Use detailed duct-network analysis, balancing calculations, manufacturer fan data, commissioning procedures, and qualified engineering review for real projects.
