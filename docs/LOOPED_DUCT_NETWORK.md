# Geometry-derived looped duct networks

CleanroomX v0.25 connects the existing duct-section pressure-loss model to the v0.23 fixed-resistance loop solver.

## Resistance derivation

For each configured duct edge, CleanroomX evaluates the section at its explicit reference airflow and derives a fixed quadratic resistance:

    R = 0.5 * rho / A^2 * (f * L / D_h + sum(K))

where:

- `rho` is the configured air density;
- `A` is duct cross-sectional area;
- `f` is the Darcy friction factor;
- `L` is straight-duct length;
- `D_h` is hydraulic diameter;
- `sum(K)` is the explicit local-loss coefficient.

The loop solver then uses:

    deltaP = R * Q * abs(Q)

The configured section airflow is a **reference condition used to establish the fixed resistance**. It is not a solved flow demand.

## Friction basis

A duct edge may use either:

- an explicit `friction_factor`; or
- `absolute_roughness_m` plus `kinematic_viscosity_m2_s`.

For automatic friction, CleanroomX resolves Reynolds number and the Darcy factor at the edge's configured reference airflow using the existing v0.21 friction workflow. That factor is then held fixed during the loop solution.

This means v0.25 is still a fixed-resistance network model. It does **not** iterate Reynolds number or Darcy friction factor as solved edge flow changes.

## Input

Each edge contains its network endpoints and one duct section:

    {
      "name": "Supply to A",
      "start_node": "Supply",
      "end_node": "Junction A",
      "section": {
        "length_m": 12.0,
        "airflow_m3_h": 3000.0,
        "air_density_kg_m3": 1.2,
        "local_loss_coefficient": 1.5,
        "diameter_m": 0.55,
        "absolute_roughness_m": 0.00009,
        "kinematic_viscosity_m2_s": 0.000015
      }
    }

The complete network must still satisfy the v0.23 requirements: valid connected topology, positive derived edge resistances, unique edge names, valid node references, and globally balanced node injections.

## CLI

Markdown report:

    cleanroomx-loop-duct examples/looped_duct_network_demo.json

JSON output:

    cleanroomx-loop-duct examples/looped_duct_network_demo.json --format json

Write a report:

    cleanroomx-loop-duct examples/looped_duct_network_demo.json --output looped-duct-report.md

## Reported evidence

For every edge CleanroomX reports:

- reference airflow;
- geometry and hydraulic diameter;
- resolved or supplied Darcy friction factor;
- friction-factor method and Reynolds number when automatic friction is used;
- derived quadratic resistance;
- reference-condition pressure drop;
- solved signed airflow and actual flow direction;
- solved pressure difference and pressure-law residual.

Node continuity residuals and the global solver residuals from the fixed-resistance loop solver are preserved.

## Engineering boundary

This workflow derives fixed edge resistance from explicit geometry and a declared reference condition. It does not infer material roughness, fluid properties, fitting coefficients, or design limits. It does not iterate flow-dependent friction during mesh balancing and does not model fans, dampers, controls, leakage, system effect, acoustics, compressibility, or transients.

Use applicable licensed standards, project specifications, manufacturer data, and qualified HVAC/cleanroom engineering review for real designs.
