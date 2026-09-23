# Loop damper-resistance scenario studies

CleanroomX v0.27 adds deterministic scenario analysis on top of the fixed-resistance loop-network solver.

## Model

Each study contains one unchanged baseline loop network plus one or more named cases. A case supplies resistance multipliers for selected edges.

For an adjusted edge:

    R_case = multiplier * R_base

The multiplier must be finite and greater than or equal to 1.0. This makes the meaning explicit: the case adds or preserves quadratic resistance. CleanroomX does not convert actuator command or blade angle into resistance.

The existing loop equation remains:

    deltaP = R * Q * abs(Q)

Each case is re-solved from the same node injections, topology, and reference node.

## Output

The result preserves the full baseline solution and full solution for every case, including signed edge flows, relative node pressures, continuity residuals, and edge pressure-law residuals.

For each case, CleanroomX also reports:

- configured edge multipliers;
- base and adjusted edge resistance;
- base resistance provenance;
- baseline versus case airflow for every edge;
- absolute and percent airflow change where a baseline flow is nonzero.

When a geometry-derived v0.25 edge is throttled, the adjusted edge is marked as damper-adjusted and its evidence retains the original geometry-derived basis and evidence.

## Run

    cleanroomx-damper-study examples/damper_study_demo.json

JSON output:

    cleanroomx-damper-study examples/damper_study_demo.json --format json

Markdown report:

    cleanroomx-damper-study examples/damper_study_demo.json --output damper-study-report.md

## Engineering boundary

This is a fixed-resistance scenario tool, not an automatic balancing controller. It does not infer damper position, local-loss coefficient, actuator behavior, control logic, leakage, variable-friction iteration, fan interaction, compressibility, or transient response. The user is responsible for supplying case multipliers from an appropriate engineering basis.
