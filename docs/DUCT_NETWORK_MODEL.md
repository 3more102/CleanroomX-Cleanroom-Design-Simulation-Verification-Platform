# Supply duct pressure-loss model

CleanroomX v0.6 adds a preliminary supply-duct pressure-loss workflow for explicitly configured candidate paths.

The engineering basis follows the pressure-loss framework described in the 2025 ASHRAE Handbook—Fundamentals, Chapter 21, *Duct Design*: duct-system resistance includes friction and dynamic losses; friction can be evaluated with the Darcy equation and Colebrook friction factor, while fitting losses are referenced to section velocity pressure.

Authoritative references:

- https://www.ashrae.org/technical-resources/ashrae-handbook
- https://www.ashrae.org/technical-resources/bookstore/duct-fitting-database

CleanroomX does not copy or embed proprietary fitting loss-coefficient tables. The user supplies the sum of applicable local loss coefficients for each section from the project design basis, licensed database/standard, manufacturer information, or measured data.

## Model inputs

A `supply_duct_network` contains:

- air density in kg/m³;
- dynamic viscosity in Pa·s;
- one or more candidate supply paths.

Each path contains one or more duct sections. Every section supplies:

- name;
- length;
- airflow;
- absolute roughness;
- optional summed local loss coefficient;
- either a round diameter, or rectangular width and height.

Shared physical sections may appear in more than one candidate path. CleanroomX currently analyzes each path independently and does not solve network flow distribution.

## Calculations

For each section, CleanroomX calculates mean velocity from `Q/A`.

For a round duct, the hydraulic diameter equals the duct diameter. For a rectangular duct, the model uses:

    D_h = 4 A / P = 2 W H / (W + H)

Reynolds number is:

    Re = rho V D_h / mu

The Darcy friction factor is calculated as:

- `64/Re` for laminar flow below Reynolds number 2300;
- iterative Colebrook solution for Reynolds number 2300 and above.

The section velocity pressure is:

    p_v = rho V^2 / 2

Straight-duct friction loss is:

    delta_p_f = f (L / D_h) p_v

Local/fitting loss is:

    delta_p_local = K p_v

and section total loss is their sum. A path loss is the sum of its section losses. The configured path with the greatest total pressure loss is reported as the critical path.

When both `supply_duct_network` and `fan_system` are present, the calculated critical-path loss is used as the fan's duct pressure component. The manual `fan_system.duct_pressure_drop_pa` remains the fallback when no duct network is configured.

## Important limitations

This is a steady-state screening model. It does not currently solve:

- automatic branch airflow distribution or balancing;
- duct leakage;
- fan system effect;
- thermal gravity/stack effects;
- diffuser/terminal throw or room air distribution;
- acoustic criteria;
- dirty-filter allowance;
- return/exhaust networks;
- compressible/high-velocity duct flow;
- detailed fitting geometry or proprietary fitting coefficients.

For Reynolds numbers in the laminar-to-turbulent transition range, the reported Colebrook-based result should be treated as a screening estimate.

Use qualified HVAC engineering review and the applicable project standards, manufacturer data, and licensed fitting references for final design.
