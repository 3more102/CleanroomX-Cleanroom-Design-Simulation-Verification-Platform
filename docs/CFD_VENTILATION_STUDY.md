# External CFD ventilation study: three NANENG 523 configurations

This feature **post-processes external CFD field samples** and compares three
cleanroom layouts from the uploaded educational document, *CFD Analysis for
Cleanroom Lab 1*, NANENG 523 (2025). It does **not** perform computational fluid
dynamics, generate a mesh, solve Navier–Stokes, or simulate contaminant transport.

## Layouts

1. Central ceiling air inlets and low-level wall exhaust.
2. Distributed ceiling air inlets and low-level wall exhaust.
3. Distributed ceiling air inlets and a perforated raised-floor exhaust.

The document describes **single-pass freshly treated air**. It reports
qualitatively that Layout 3 has less recirculation and more direct downward
contaminant removal. These observations are *source claims*, not validated
numerical output supplied with the document.

## Command

After installing with pip:

    cleanroomx-cfd-study examples/cfd_three_configurations_template.json

A template without CFD results exits with code **3** and reports
"insufficient_evidence". It does *not* select Configuration 3 as a default.

Write a protected JSON report:

    cleanroomx-cfd-study my-cfd-study.json --output cfd-comparison.json

Exit codes: 0 = three comparable evaluated cases; 3 = insufficient evidence
for a comparison (or failed comparability gate); 1 = output publication error;
input/validation errors follow the shared CleanroomX CLI error boundary.

## Input contract (schema cleanroomx.cfd-study.v1)

- room: length_m, width_m, height_m, all positive, in metres; can be null in
  an uncomputed study template.
- analysis: user-supplied contaminant_limit and contaminant_unit,
  max_unrepresented_volume_fraction, max_flow_imbalance_fraction.
- cases: one to three entries with unique configuration values (1, 2, 3).
- Per case: source_location_m [x,y,z], inlet_flow_m3_s,
  outlet_flow_m3_s, solver metadata, and optional sampled CFD cells.
- solver: name, run_id, mesh_cells, source_reference.
- Each cell: volume_m3, velocity_m_s [u,v,w], optional
  contaminant_concentration, optional recirculating Boolean from the
  external solver's streamline/recirculation analysis.
- Optional exhaust_capture_fraction is only accepted as a supplied external
  result, never inferred from velocity fields.

One sample may represent an external CFD cell or a disjoint, spatially
aggregated region. Sample volumes must **not overlap**, or the volume-based
metrics are invalid; the software checks their total against room volume but
cannot independently prove non-overlap. The source CFD solver and export
pipeline must establish field/mesh correspondence, sampling coverage,
velocity/scalar units, recirculation method, mesh independence and convergence.

### Example populated cell (illustrative only, NOT a solver result)

    {
      "volume_m3": 0.1,
      "velocity_m_s": [0.0, 0.0, -0.2],
      "contaminant_concentration": 4.2,
      "recirculating": false
    }

No regulatory concentration limit is inferred. All test values in the software
regression tests are explicitly synthetic.

## Analysis and fairness gates

Volume-weighted calculations produce:
- average flow speed in m/s;
- coefficient of variation of speed (not a turbulence or full uniformity model);
- fraction of **sampled volume** externally labelled recirculating;
- volume-weighted mean and maximum concentration;
- fraction of sampled volume above the *project-specified* concentration limit;
- supply/exhaust flow discrepancy relative to supply;
- source input SHA-256 for deterministic evidence association.

A three-way comparison is gated on required fields, matched source location,
identical specified inlet/outlet flow conditions, a matching solver name,
complete metrics and project-specified coverage/balance tolerances. The
"unique_pareto_dominant_configuration" is assigned only when a single case
weakly dominates every other case in all three minimization metrics and
strictly improves at least one metric against each competitor. Trade-offs and
ties result in no unique winner. A comparable run does not constitute
certification, field validation, or real-world performance proof.

**Limitations:** no geometry synthesis, CAD/IFC boundary extraction, CFD mesh,
solver invocation, turbulent-flow closure, transient simulation, particle
trajectory calculation, streamline analysis, filter-physics model, or
regulatory qualification in this first integration. Additional physical
validation is required before design decisions.
