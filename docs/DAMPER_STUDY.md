# Damper case study

CleanroomX v0.27 adds a bounded steady-state study for comparing explicit damper-resistance cases on the existing looped airflow-network solver.

## Model

A damper setting is represented only by a user-supplied additional fixed quadratic resistance on a named loop edge:

    R_total = R_base + R_damper
    deltaP_damper = R_damper * Q * abs(Q)

where resistance is in Pa/(m3/s)^2 and Q is the solved signed edge airflow in m3/s.

The base edge resistance may come from the existing explicit-resistance workflow or from v0.25 geometry-derived resistance. The damper addition is then applied as a separate fixed case input.

An optional position percentage and setting label may be recorded for traceability. They are descriptive metadata only. CleanroomX does not infer resistance from damper position.

## Input

Each study contains:

- one existing looped airflow network;
- one or more named cases;
- one or more damper settings per case;
- for each setting, a target edge name and explicit added quadratic resistance;
- optional position percentage from 0 to 100 and a descriptive setting label.

Example:

    {
      "name": "Supply balancing cases",
      "loop_network": { "...": "existing v0.25 loop input" },
      "cases": [
        {
          "name": "Throttle branch B",
          "settings": [
            {
              "edge_name": "Supply to B",
              "added_resistance_pa_per_m3_s_squared": 180.0,
              "position_percent": 60.0,
              "setting_label": "user/manufacturer case"
            }
          ]
        }
      ]
    }

## Run

    cleanroomx-damper-study examples/damper_study_demo.json

JSON output:

    cleanroomx-damper-study examples/damper_study_demo.json --format json

Write a Markdown report:

    cleanroomx-damper-study examples/damper_study_demo.json --output damper-study-report.md

## Reported evidence

For the baseline and every case, CleanroomX preserves the complete loop-network solution and residuals. The study also reports:

- baseline and case pressure span;
- pressure-span change from baseline;
- base, added, and total resistance for every configured damper edge;
- solved airflow and flow direction through each configured damper edge;
- the damper-only pressure-difference contribution at the solved flow;
- per-edge airflow change from baseline.

## Engineering boundary

This is a deterministic case comparison, not an automatic balancing or control solver. Node injections remain fixed across all cases. Damper resistance is supplied by the user and held fixed within each case.

CleanroomX does not create a position-to-loss curve, infer a loss coefficient from position, optimize damper positions, execute a control law, iterate flow-dependent friction, couple a fan curve in this workflow, model leakage/system effect/compressibility/transients, or define commissioning acceptance limits. Damper loss inputs should come from applicable manufacturer data, measured characterization, project design basis, or another documented source.
