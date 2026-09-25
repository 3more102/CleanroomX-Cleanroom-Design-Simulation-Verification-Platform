# Room Pressure / Leakage Network

CleanroomX provides a steady-state multizone room-pressure solver for explicit
mechanical airflows and pressure-dependent leakage/opening paths.

The model is intended for engineering screening and design iteration. It does not
infer leakage coefficients, opening areas, discharge coefficients, wind pressure,
stack pressure, door-event transients, commissioning/TAB results, or certification
requirements.

## Supported nodes

Each node represents a room, corridor, exterior/reference space, or other pressure
zone.

For each node the input may define:

- supply airflow in m³/h;
- return airflow in m³/h;
- exhaust airflow in m³/h;
- an optional fixed pressure in Pa.

At least one fixed-pressure node is required, and every unknown-pressure node must
be connected to a fixed-pressure boundary through configured pressure paths.

Mechanical injection is explicit:

```text
mechanical injection = supply - return - exhaust
```

## Pressure paths

Supported semantic path kinds include doors, windows, undercuts, transfer grilles,
pass boxes, penetrations, cracks, intentional leakage, and generic openings. The
semantic kind does not invent flow characteristics. Every path must explicitly
select and parameterize one flow model.

### Power-law model

```text
Q = C * sign(ΔP) * |ΔP|^n
```

where:

- `Q` is volumetric airflow in m³/s;
- `C` is the user-supplied flow coefficient in m³/s/Paⁿ;
- `ΔP` is the effective path pressure difference in Pa;
- `n` is the user-supplied flow exponent.

CleanroomX accepts exponents from 0.5 to 1.0 for this model.

### Orifice model

```text
Q = Cd * A * sign(ΔP) * sqrt(2 * |ΔP| / ρ)
```

where:

- `Cd` is the user-supplied discharge coefficient;
- `A` is the user-supplied opening area in m²;
- `ρ` is the user-supplied air density in kg/m³.

The power-law and orifice forms are established multizone-airflow relationships.
See:

- NIST CONTAMW User Manual, NISTIR 6476, section 5.3.3:
  https://tsapps.nist.gov/publication/get_pdf.cfm?pub_id=860813
- NIST CONTAM User Guide and Program Documentation:
  https://www.nist.gov/publications/contam-user-guide-and-program-documentation-version-34
- EnergyPlus AirflowNetwork Input/Output Reference:
  https://energyplus.net/assets/nrel_custom/pdfs/pdfs_v23.1.0/InputOutputReference.pdf

These references support the mathematical model form; they do not supply
project-specific CleanroomX coefficients.

## Near-zero pressure regularization

The derivative of nonlinear pressure-flow laws becomes problematic as ΔP approaches
zero. Each path therefore has an explicit `linearization_pressure_pa`. Below that
magnitude CleanroomX uses a linear continuation matched to the configured nonlinear
law at the transition pressure.

The transition value is retained in result evidence for every path.

## Pressure offsets

`pressure_offset_pa` is an optional explicit path input added to the node-pressure
difference before evaluating the flow law. It can represent an externally computed
driving-pressure contribution.

CleanroomX does not calculate wind or stack pressure automatically in this release.

## Pressure targets

Targets can define:

- high-pressure node;
- low-pressure node;
- minimum differential pressure;
- optional maximum differential pressure.

Target failures do not prevent the physical network from solving. The result status
becomes `solved_with_target_violations` and every failed target is retained
explicitly.

## Solver

Unknown room pressures are solved simultaneously using a damped Newton method.

The result preserves:

- solver method;
- iteration count;
- configured iteration limit;
- mass-balance tolerance;
- maximum unknown-node mass-balance residual;
- every solved node pressure;
- every pressure-path airflow and direction;
- local path dQ/dP sensitivity;
- dominant pressure path for each node;
- fixed-boundary balancing flow;
- pressure-target margins.

Non-convergence raises an error rather than returning a false solved result.

## Example

Run the repository example:

```bash
cleanroomx-pressure-network examples/pressure_network_demo.json
```

JSON output:

```bash
cleanroomx-pressure-network examples/pressure_network_demo.json --format json
```

The same workflow is registered in the desktop application as
**Room pressure network** under **Networks**.

## Engineering boundary

This is a steady-state, well-mixed multizone pressure-network model. It is not CFD
and does not resolve local velocity fields, turbulence, recirculation, contaminant
transport within a room, or transient door-opening behavior.

Leakage/opening parameters and acceptance targets must come from project-specific
engineering data, measurements, product data, or explicitly selected design
assumptions.
