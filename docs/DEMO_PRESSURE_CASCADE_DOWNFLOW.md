# CleanroomX connected-door 5 Pa cascade / ceiling downflow demo

This document describes a **synthetic engineering design demonstration**.
It is **not** a measured/commissioned cleanroom, a 3-D CFD solution, a validated
laminar-flow field, or evidence of ISO 14644 compliance.

## Launch

On the branch containing this demo, from the repository checkout:

```powershell
.\start-cleanroomx.ps1
```

Or, with the installed project package for this branch:

```powershell
cleanroomx-gui --demo
```

The checked-in copy is `examples/gui_demo.cleanroomx.json` and the bundled
default is `src/cleanroomx/demo/gui_demo.cleanroomx.json`.

## Conceptual geometry (door CLOSED)

```text
 [Process +15 Pa] |door| [Preparation +10 Pa] |door| [Ante +5 Pa] |door| [Corridor 0 Pa]
       FFUs ↓                  FFUs ↓                   FFUs ↓
   low-wall return        low-wall return          low-wall return
```

The rooms abut at shared walls (east side of the higher pressure room).
The three door devices are positioned on those walls, rather than on the
outside walls of isolated rooms. There are 12 ceiling-mounted FFU icons
and 3 low-level return icons. The pressure labels are scenario design
inputs; they are not live sensor readings.

## Pressure-network engineering screening

The bundled project also includes an executable **Room pressure network**
analysis named `Door leakage network | 5 Pa steps (synthetic)`, selected as
the default active analysis.

- Nodes: Process, Preparation, Ante and reference Corridor (fixed 0 Pa gauge).
- Closed-door leakage paths: Process → Preparation → Ante → Corridor.
- Each path uses assumed `Q = C × sign(ΔP) × |ΔP|^n` with
  `C = 0.002 m³/(s·Pa)`, `n = 1`, and `0.01 Pa` near-zero regularization.
- Process mechanical supply/return: 2700 / 2664 m³/h, leaving 36 m³/h
  net transfer through the assumed leakage network.
- Preparation and Ante use zero modeled net mechanical injection.
- A nominal 5 Pa step gives `Q = 0.002 × 5 = 0.01 m³/s = 36 m³/h`
  along each assumed closed-door leakage path.
- Three pressure targets: minimum 5 Pa between adjacent zones.

These values are deliberately *calibrated assumptions to illustrate*
the solver and cannot be used as door leakage or airflow specifications.
The fixed-pressure Corridor balancing flow is supplied by the
reference boundary; there is no independent corridor ventilation design.

## Downflow limitations

The ceiling FFUs and low returns express the intended **top-to-bottom
unidirectional air pattern**. The spatial 3-D view draws dashed cyan **design-intent downflow arrows** beneath
ceiling FFUs (tagged `design-downflow`); they are illustrations, not
computed velocity vectors, streamlines, or a resolved CFD flow field.

To establish a real laminar/unidirectional flow field: specify actual FFU
face area, velocity/flow and recirculation details, return boundary
conditions, doors and leakage geometry; generate a valid 3-D mesh; run
OpenFOAM and evaluate the flow field with postprocessing. Pressure
cascade values and downflow uniformity require independent validation.

See `docs/PRESSURE_NETWORK.md` for the supported screening method and
limitations, including the underlying NIST CONTAM reference.
