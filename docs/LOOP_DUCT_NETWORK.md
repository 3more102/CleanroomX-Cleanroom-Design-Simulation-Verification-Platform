# Geometry-derived looped airflow networks

CleanroomX v0.25 bridges the v0.21 duct/friction calculations and the v0.23 fixed-resistance loop solver. It derives each loop edge's fixed quadratic resistance from explicit duct geometry and loss inputs, then solves the resulting connected pressure network.

## Model

Each geometry-derived loop edge contains:

- a declared positive reference airflow;
- one or more duct sections in series;
- air density, geometry, length, and local loss coefficient for every section;
- either an explicit Darcy friction factor, or explicit roughness plus kinematic viscosity for automatic Darcy friction.

For a section, CleanroomX evaluates the fixed quadratic resistance

    R_section =
        0.5 * rho / A^2
        * (f * L / D_h + K)

so that

    deltaP_section = R_section * Q * abs(Q)

Sections on the same edge carry the same airflow, therefore their fixed resistances add:

    R_edge = sum(R_section)

The derived edge is passed to the existing v0.23 pressure-node solver without changing that solver's constitutive law.

## Reference airflow and automatic friction

The edge-level `reference_airflow_m3_h` is the airflow basis used for every section on that edge.

For an explicit user-supplied Darcy factor, the fixed-resistance equation is directly determined by the supplied factor and geometry.

For automatic friction, CleanroomX evaluates Reynolds number and resolves the Darcy factor at the declared reference airflow using the existing v0.21 friction workflow. That resolved factor is then held fixed while the loop network is balanced.

The reference airflow is therefore **not** a forced solved flow and it is not an acceptance target. Reports include the absolute solved/reference airflow ratio as evidence of how far the operating solution lies from the friction-resolution basis.

## Input structure

Example edge:

    {
      "name": "Supply to A",
      "start_node": "Supply",
      "end_node": "Junction A",
      "reference_airflow_m3_h": 3000.0,
      "sections": [
        {
          "name": "SA round duct",
          "length_m": 12.0,
          "friction_factor": 0.020,
          "air_density_kg_m3": 1.2,
          "local_loss_coefficient": 1.4,
          "diameter_m": 0.55
        }
      ]
    }

When automatic friction is selected, omit `friction_factor` and provide both:

    "absolute_roughness_m": 0.00009,
    "kinematic_viscosity_m2_s": 0.000015

Section-level `airflow_m3_h` is intentionally rejected in this workflow. The edge reference airflow is the single auditable friction basis for all series sections on that edge.

## CLI

Run the example:

    cleanroomx-loop-duct examples/loop_duct_network_demo.json

JSON output:

    cleanroomx-loop-duct examples/loop_duct_network_demo.json --format json

Write a Markdown report:

    cleanroomx-loop-duct examples/loop_duct_network_demo.json --output loop-duct-report.md

The report includes:

- solved node pressures and continuity residuals;
- solved signed edge airflow;
- derived edge resistance;
- reference airflow and absolute solved/reference airflow ratio;
- per-section Darcy factor, friction method, Reynolds number when applicable, section resistance, and reference pressure drop.

## Scope boundary

This workflow is a geometry-to-fixed-resistance preprocessing layer followed by the existing fixed-resistance steady-state loop solver.

It does **not** iterate the Darcy factor as the loop solution changes, infer roughness or fluid properties, infer fitting coefficients, solve balancing-damper positions, model leakage, couple a fan curve into the mesh, model compressibility or transients, or establish commissioning acceptance.

If the solved airflow differs materially from the reference airflow on an automatic-friction edge, the report exposes that ratio but does not invent an engineering acceptance threshold. A qualified engineer must decide whether the fixed-friction approximation is appropriate for the project.
