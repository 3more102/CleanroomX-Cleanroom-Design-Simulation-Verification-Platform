# Fan-curve integration with a reference duct network

CleanroomX v0.14 links the bounded v0.11 fan-curve solver to the
path-based duct model. It derives a quadratic system resistance from
explicit duct geometry, Darcy friction factors, air density, local-loss
coefficients, and a user-supplied reference flow distribution.

## Reference-flow scaling

The study defines a reference total system airflow:

    Q_system,ref

Each duct section already contains a reference section airflow:

    Q_i,ref

CleanroomX forms the explicit section flow fraction:

    alpha_i = Q_i,ref / Q_system,ref

For a trial total system airflow Q, the section airflow is assumed to
scale proportionally:

    Q_i = alpha_i * Q

With constant air density, Darcy friction factor, geometry, and local
loss coefficient, each section pressure drop remains quadratic in flow:

    delta_p_i =
        0.5 * rho_i *
        (f_i * L_i / D_h,i + K_i) *
        (Q_i / A_i)^2

Substituting the fixed flow fraction gives a section contribution to the
system-curve coefficient:

    R_i =
        0.5 * rho_i *
        (f_i * L_i / D_h,i + K_i) *
        alpha_i^2 / A_i^2

with R_i in Pa/(m3/s)^2 when Q is in m3/s.

The resistance of a supplied path is the sum of its section
contributions. The path with the largest derived resistance is the
critical path for this fixed-ratio model.

## System curve and operating point

The fan sees:

    delta_p_system = delta_p_fixed + R_critical * Q^2

The fixed pressure term is an explicit project input for pressure
components the user deliberately treats as flow-independent in this
screening model.

The existing CleanroomX fan solver then intersects this system curve
with the user-supplied fan performance points. Fan pressure is
piecewise-linearly interpolated only inside the supplied fan-curve
range; no extrapolation is performed.

At the solved operating point, CleanroomX reports:

- fan airflow and pressure;
- system pressure and pressure residual;
- critical path and derived resistance;
- reference and operating pressure drop for every supplied path;
- reference and operating airflow/drop for every section;
- fluid air power from Q times total system pressure.

## Important modeling boundary

This workflow does **not** solve a new duct-flow distribution as the fan
operating point changes. It holds every section's reference airflow
fraction constant. That assumption is explicit and auditable.

It therefore does not replace:

- the v0.8 fixed-demand branch-flow solver;
- the v0.9 simple passive parallel-path solver;
- a general nonlinear looped-network solver;
- Reynolds-number/friction-factor iteration;
- balancing damper or leakage modeling;
- system-effect corrections;
- fan stall/surge evaluation;
- VFD/control modeling;
- manufacturer fan selection or qualified HVAC engineering review.

A section reference airflow greater than the reference total system
airflow is rejected.

## Engineering dossier integration

CleanroomX v0.17 can include one or more reference-flow fan/duct studies in an engineering dossier through `fan_duct_network_studies`. Each source is SHA-256 fingerprinted; the dossier reports the critical path and solved operating point, while a no-intersection result becomes an attention item without fan-curve extrapolation.

## JSON input

    {
      "name": "Fan and duct-network operating-point demo",
      "reference_system_airflow_m3_h": 900.0,
      "fixed_pressure_pa": 80.0,
      "fan_curve": {
        "name": "Example fan",
        "points": [
          {"airflow_m3_h": 0.0, "pressure_pa": 600.0},
          {"airflow_m3_h": 3000.0, "pressure_pa": 500.0},
          {"airflow_m3_h": 6000.0, "pressure_pa": 300.0}
        ]
      },
      "duct_network": {
        "paths": [
          {
            "name": "Supply path",
            "sections": [
              {
                "name": "Main",
                "length_m": 10.0,
                "airflow_m3_h": 900.0,
                "friction_factor": 0.02,
                "air_density_kg_m3": 1.2,
                "local_loss_coefficient": 2.0,
                "width_m": 0.5,
                "height_m": 0.25
              }
            ]
          }
        ]
      }
    }

Run:

    cleanroomx-fan-duct examples/fan_duct_network_demo.json

JSON output:

    cleanroomx-fan-duct examples/fan_duct_network_demo.json --format json

## References

- ASHRAE Handbook—Fundamentals: duct friction and dynamic-loss methods.
- ASHRAE Handbook—HVAC Systems and Equipment, Fans: fan/system
  operating-point concepts.
- U.S. Department of Energy, Improving Fan System Performance: A
  Sourcebook for Industry.

Use current licensed standards, project requirements, and manufacturer
data for real projects.
