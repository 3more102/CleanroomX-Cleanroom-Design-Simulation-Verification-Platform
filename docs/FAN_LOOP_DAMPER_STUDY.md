# Fan-driven loop damper study

CleanroomX v0.27 adds discrete damper-state studies on top of the v0.26 bounded fan/loop-network coupling workflow.

## Model

Each damper state supplies an explicit additive quadratic resistance for one or more existing loop-network edges:

    R_adjusted = R_base + R_damper_added

The adjusted network remains a fixed-resistance network using:

    deltaP = R_adjusted * Q * abs(Q)

For each state CleanroomX derives the two-terminal equivalent loop resistance, intersects it with the supplied fan curve without extrapolation, and re-solves the full loop at the operating airflow.

## Why resistance is explicit

CleanroomX does not convert damper opening percentage, actuator command, or blade angle into a pressure-loss coefficient. That relationship depends on the specific damper geometry and manufacturer/test data. The user therefore supplies the added fixed quadratic resistance for each state from an applicable design basis or measured/manufacturer data.

Zero added resistance is allowed so an explicitly named baseline/open state can be included.

## Input shape

    {
      "name": "Damper sweep",
      "base_study": { "...": "same schema as cleanroomx-fan-loop" },
      "damper_states": [
        {
          "name": "Open",
          "edge_added_resistance_pa_per_m3_s_squared": {"Branch A": 0.0}
        },
        {
          "name": "Throttled",
          "edge_added_resistance_pa_per_m3_s_squared": {"Branch A": 1500.0}
        }
      ]
    }

## Run

    cleanroomx-fan-damper examples/fan_loop_damper_demo.json

JSON output:

    cleanroomx-fan-damper examples/fan_loop_damper_demo.json --format json

Markdown report:

    cleanroomx-fan-damper examples/fan_loop_damper_demo.json --output fan-damper-report.md

## Reported evidence

- explicit base, added, and adjusted edge resistance for each configured damper state;
- equivalent loop resistance for each state;
- bounded fan operating airflow and pressure when an intersection exists;
- full solved edge flows and directions from the operating network;
- inherited continuity, pressure-law, equivalent-network, and fan/system residual evidence.

## Engineering boundary

This is a discrete steady-state sensitivity study. Added damper resistance is fixed inside each state. The workflow does not infer a continuous control characteristic, solve a target-flow damper position, iterate flow-dependent friction, model actuator dynamics, leakage, acoustics, system effect, compressibility, or transients. It does not replace manufacturer data, detailed HVAC design, TAB/commissioning, or qualified engineering review.
