# Variable-friction loop solver

CleanroomX v0.27 adds an optional outer iteration around the existing looped-network pressure solver.

## Purpose

The v0.25 geometry loader can derive an edge resistance from duct geometry and either a user-supplied Darcy friction factor or automatic friction inputs. Before v0.27, automatic friction was resolved once at the declared reference airflow and then held fixed.

The v0.27 workflow is for loop-network inputs that already use automatic friction from explicit:

- duct geometry;
- air density;
- local loss coefficient;
- absolute roughness;
- kinematic viscosity;
- reference airflow.

For those edges, CleanroomX now re-evaluates Darcy friction at the absolute solved edge airflow, rebuilds the corresponding quadratic resistance, and repeats the loop solve until resistance closure is reached.

## Algorithm

Each outer iteration:

1. solves the full connected loop network with the current edge resistances;
2. reads the absolute solved airflow of each automatic-friction geometry edge;
3. recomputes Reynolds number and Darcy friction using the existing friction model;
4. derives the target Darcy-Weisbach plus local-loss resistance;
5. optionally relaxes the friction-factor update;
6. repeats until the maximum relative difference between used and target automatic-edge resistance is within the configured tolerance.

The inner mesh solve remains the validated damped-Newton fixed-resistance solver. Its node mass-balance and edge pressure-law residuals remain reported.

## Fixed edges

The new solver intentionally does not alter:

- directly supplied resistance values;
- geometry-derived resistance that uses a user-supplied Darcy friction factor.

This preserves the behavior and meaning of existing v0.23-v0.26 inputs.

## Near-zero flow

Reynolds-based friction is undefined at exactly zero velocity. If an automatic-friction edge solves at or below the configured near-zero airflow threshold, its previous resistance is retained and the output marks the edge as near_zero_flow_frozen.

The pressure loss of such a branch is already negligible at the solved state. CleanroomX does not invent a Reynolds number or friction factor for zero flow.

## Laminar boundary

The existing friction model uses 64/Re for circular laminar ducts and Colebrook for Re >= 2300. Automatic laminar friction for noncircular ducts remains unsupported. If an iterated rectangular edge enters that unsupported regime, the solver stops with an explicit validation error rather than silently applying a circular correlation.

## Run

    cleanroomx-loop-friction examples/variable_friction_loop_demo.json

JSON output:

    cleanroomx-loop-friction examples/variable_friction_loop_demo.json --format json

Tighter resistance closure with full updates:

    cleanroomx-loop-friction examples/variable_friction_loop_demo.json --resistance-relative-tolerance 1e-7 --relaxation 1.0

## Engineering boundary

This is a steady-state airflow-network calculation with iterative Darcy friction only. Air density and local loss coefficients remain fixed inputs. The solver does not infer damper positions, control logic, leakage, system-effect correction, fan behavior, acoustics, compressibility, or transient response. It does not replace detailed duct design, manufacturer data, commissioning, or qualified engineering review.
