# Duct critical-path pressure-loss model

CleanroomX v0.6 adds a transparent path-based duct pressure-loss calculation for preliminary cleanroom HVAC design.

## Section calculation

Each duct segment uses explicit project inputs for airflow, air density, Darcy friction factor, length, geometry, and the local loss coefficient for fittings or components assigned to that segment.

Velocity pressure is:

    q = 0.5 * rho * V^2

Straight-duct friction uses the Darcy-Weisbach form:

    delta_p_f = f_D * (L / D_h) * q

Local losses are:

    delta_p_local = K * q

For rectangular ducts, CleanroomX uses:

    D_h = 4A / P = 2ab / (a + b)

For round ducts, the hydraulic diameter is the inside diameter.

## Path and network calculation

A path is an explicit fan-to-terminal series route. CleanroomX sums segment losses for every configured path and identifies the route with the largest calculated pressure loss as the critical path.

This is intentionally a **critical-path pressure-loss model**, not a nonlinear network-balancing solver. Shared segments may be repeated in multiple paths and branch airflow is not inferred.

## Engineering boundaries

- Segment airflow is an explicit project input.
- Darcy friction factor is an explicit input; v0.6 does not infer roughness/Reynolds number or solve Colebrook.
- Local loss coefficients are explicit inputs; use project/manufacturer data or an applicable licensed fitting database.
- The model does not determine fan operating point, system effect, leakage, acoustic performance, balancing-damper position, controls, redundancy, or commissioning acceptance.
- The calculation is preliminary engineering screening and does not replace detailed duct design or qualified engineering review.

## References

ASHRAE Handbook—Fundamentals, Chapter 21, Duct Design describes friction and dynamic losses, the Darcy/Colebrook formulation, and hydraulic diameter for noncircular ducts:

- https://handbook.ashrae.org/Handbooks/F25/IP/F25_Ch21/F25_Ch21_ip.aspx

ASHRAE's Duct Fitting Database provides fitting loss-coefficient data and references Standard 120 test methods:

- https://www.ashrae.org/technical-resources/bookstore/duct-fitting-database

Use the current applicable licensed standard, project specification, local regulations, and manufacturer data for real projects.
