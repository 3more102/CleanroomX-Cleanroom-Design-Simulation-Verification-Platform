# Automatic Darcy friction-factor resolution

CleanroomX v0.20 can calculate a Darcy friction factor from explicit duct roughness and kinematic viscosity instead of requiring a fixed factor on every section.

## Inputs

Automatic mode is selected by omitting `friction_factor` and supplying both `absolute_roughness_m` and `kinematic_viscosity_m2_s`. Airflow, density, and geometry remain explicit project inputs.

A section must use one mode only: a direct `friction_factor`, or the automatic roughness/viscosity inputs.

## Flow-regime policy

The implementation uses:

- `f = 64/Re` only for circular laminar flow with Re < 2300;
- no automatic factor for 2300 <= Re < 4000; an explicit project friction factor is required;
- the Darcy-form Colebrook equation for Re >= 4000;
- an explicit friction factor for noncircular laminar flow rather than applying the circular-pipe relation.

The transition guard is intentional: the software does not invent a friction factor in the unstable laminar/turbulent transition range.

## Colebrook relation

    1/sqrt(f) = -2 log10(epsilon/(3.7 Dh) + 2.51/(Re sqrt(f)))

where `epsilon` is the supplied absolute roughness and `Dh` is hydraulic diameter.

## Integration

Automatic friction is supported in duct critical-path analysis, fixed-demand branch trees, and reference-flow fan/duct studies. Branch-tree friction is resolved at each solved branch airflow. Reference-flow fan/duct studies resolve friction at each section's declared reference airflow and then preserve that factor in the existing fixed-R quadratic scaling.

The analytical passive parallel-flow solver still requires explicit fixed friction factors because its closed-form solution assumes constant `R` in `delta_p = R Q^2`.

## Engineering boundary

CleanroomX does not infer roughness, viscosity, fouling, aging, fitting coefficients, leakage, system effect, or acceptance limits. Use project data and qualified engineering references for real designs.

## References

- NIST Reference Building Plumbing Model documentation describes a transition Reynolds-number range where no loss calculation is made.
- ASHRAE Handbook duct and fan guidance remains the engineering context for the CleanroomX HVAC models.
