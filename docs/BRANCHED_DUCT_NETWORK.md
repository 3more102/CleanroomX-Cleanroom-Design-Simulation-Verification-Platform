# Branched supply-duct network

CleanroomX v0.8 adds deterministic branch-flow aggregation for preliminary supply-duct analysis. It complements the v0.6 user-defined path model without changing that legacy input format.

## Model

A branched network is represented as a rooted, directed supply tree:

- one `root_node`, normally the AHU/fan discharge side of the modeled ductwork;
- directed duct branches from `parent_node` to `child_node`;
- one terminal room assigned to every leaf node;
- exactly one incoming branch for every non-root node.

The topology is rejected when branches are disconnected from the root, a child has multiple incoming branches, terminals do not map one-to-one to leaves, or the root has an incoming branch.

## Airflow aggregation

The HVAC analysis first determines each room's governing supply airflow from the existing CleanroomX cleanroom/makeup/thermal comparison.

For a terminal room, that governing airflow is its terminal demand. For each upstream branch:

    branch airflow = sum(all downstream terminal room demands)

This means a common trunk automatically carries the sum of the rooms it serves, while a terminal branch carries only the demand downstream of that branch.

The solver requires the branched network to cover every HVAC room in the project. This prevents a room demand from being silently omitted from the network calculation.

## Pressure loss

After branch airflow is derived, each branch reuses the existing CleanroomX section model:

    velocity = volumetric airflow / area

    velocity pressure = 0.5 * air density * velocity^2

    friction loss = Darcy friction factor * (length / hydraulic diameter) * velocity pressure

    local loss = sum(K) * velocity pressure

The pressure drop from the root to every terminal is the sum of branch losses along that terminal path. The terminal with the largest calculated root-to-terminal loss is reported as the controlling path and is used as the duct-pressure component in preliminary fan sizing.

## JSON input

Use `branched_duct_network` instead of the legacy `duct_network` field:

    {
      "branched_duct_network": {
        "root_node": "AHU",
        "branches": [
          {
            "name": "Main trunk",
            "parent_node": "AHU",
            "child_node": "J1",
            "length_m": 18.0,
            "friction_factor": 0.02,
            "air_density_kg_m3": 1.2,
            "local_loss_coefficient": 1.8,
            "width_m": 0.8,
            "height_m": 0.45
          }
        ],
        "terminals": [
          {
            "room_name": "Process Bay",
            "node": "Process terminal"
          }
        ]
      }
    }

A project cannot configure both `duct_network` and `branched_duct_network` at the same time.

Run the example with:

    cleanroomx-hvac examples/branched_duct_network_demo.json

## Engineering boundary

This is a rooted-tree demand aggregation and pressure-loss calculation, not a pressure-driven nonlinear airflow-network solution. It does not infer branch flow from pressure balance, solve fan/system operating points, select balancing-damper positions, estimate leakage, infer fitting coefficients or friction factors, evaluate acoustics, or replace commissioning.

Friction factors, local loss coefficients, geometry, and air density remain explicit engineering inputs. Use project/manufacturer data and the applicable licensed references.

## Reference

The 2025 ASHRAE Handbook—Fundamentals, Chapter 21, Duct Design covers duct-system flow resistance, frictional and dynamic losses, nodes/sections, and critical-path analysis:

https://handbook.ashrae.org/Handbooks/F25/IP/F25_Ch21/F25_Ch21_ip.aspx
