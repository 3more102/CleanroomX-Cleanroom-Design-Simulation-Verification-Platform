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
analysis named `Door leakage network | 5 Pa steps (synthetic)`.
The default active **Facility verification** analysis preserves the spatial
2-D and 3-D pressure-cascade arrow overlays; select the pressure-network
analysis explicitly when running its nonlinear leakage solver.

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


## New: room-resolved OpenFOAM case preparation (separate room solves)

Unlike the 2D/3D demonstration overlay, the following command generates real
OpenFOAM Foundation v10 `blockMeshDict`, `0/U` and `0/p` solver input files
for each FFU-supplied room (Process, Preparation, Ante). Use the checked-out
feature branch of CleanroomX:

```powershell
python -m cleanroomx.cfd_pipeline_cli project-rooms-generate examples/gui_demo.cleanroomx.json cfd_5pa_rooms --kinematic-viscosity-m2-s 1.5e-5 --mesh-cells 24 24 12
```

Or use `cleanroomx-cfd-pipeline` if its console script is installed.

The kinematic-viscosity value above is an illustrative air-property input,
**not a measurement**. Replace it with a value suited to the actual operating
temperature. The CFD converter does **not** invent this physical parameter.
It requires one explicitly.

For each exported room, the mesh boundaries classify:

- `inlet`: discrete ceiling rectangles derived from actual FFU locations in
  the spatial layout; downward velocity is calculated from the configured
  supply flow divided by mesh-resolved inlet area
- `outlet`: discrete low west-wall return grille faces, with a local numerical
  pressure reference
- `closedDoors`: door-shaped **noSlip solid wall** regions on *both sides* of
  each shared wall, covering exactly the same nominal physical doorway
- `walls`: all remaining no-slip building-envelope faces

These are discrete boundary-face approximations. The manifest reports
face counts, resolved areas, door positions, FFU counts, and SHA-256 hashes
for all input files. The exported directory is never overwritten.

OpenFOAM must be installed in Linux/WSL to opt into execution:

```powershell
python -m cleanroomx.cfd_pipeline_cli project-rooms-run cfd_5pa_rooms --timeout-seconds 3600
```

The command invokes `blockMesh`, `checkMesh` and `simpleFoam` per room
and records the output logs. It **does not** execute OpenFOAM during
generation or infer convergence merely from successful process exit.

### Critical physical separation

A closed door does **not** provide an open fluid connection in these room
CFD cases. The 5 Pa corridor/airlock/process pressure cascade remains a
**separate, steady, lumped leakage-network calculation** under synthetic
leakage assumptions. It is *not* applied as a pressure boundary condition
to these independent room CFD cases. The pressure field written to `0/p`
uses OpenFOAM kinematic pressure units, and a local zero reference at each
return; it is **not** the displayed absolute 15/10/5/0 Pa gauge cascade.

Consequently, the nominal network leakage mass balance (e.g., Process
36 m³/h net transfer at 5 Pa) is not reproduced by the isolated CFD model:
each room's unconstrained outlet flows the volume required to balance its
inlet. The two models must not be combined or represented as coupled physics.

For actual coupled airflow through an **open door**, or leakage through a
physical closed-door gap, a separate conformal multiroom mesh with
appropriate apertures/gap conductance and physically specified boundary
conditions is needed. The single-room generator does not construct that
coupling. The same applies to unverified claims of uniform laminar
downflow and the real ceiling FFU operating speed.

