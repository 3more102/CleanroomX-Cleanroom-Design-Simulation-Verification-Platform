CLEANROOMX
Engineering User & Operations Manual
Industry-oriented guide for design, simulation, verification, BIM/IFC, evidence, handoff, and controlled engineering use
[[COVER_END]]

# Document Control and Applicability

| Field | Controlled value |
| --- | --- |
| Document ID | CRX-UM-001 |
| Revision | Rev A |
| Issue date | 30 September 2026 |
| Primary production baseline | CleanroomX v0.102.1 |
| Documentation snapshot | `main` at `c9d539b81fccee19eeaf6380ea83d5ce1729a77b` |
| Package version on snapshot | 0.102.1 |
| Supported Python | 3.11 / 3.12 / 3.13 |
| Project schema | `cleanroomx.project`, schema version 1 |
| Stable release validation anchor | 1008 passing tests on Python 3.11, 3.12, and 3.13 at the final v0.102.1 spatial release gate |
| Intended audience | Cleanroom designers, HVAC engineers, BIM coordinators, reviewers, QA/verification personnel, technical leads, and developers supporting controlled deployments |
| Repository | `3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform` |

> [!CONTROL] This manual separates the validated v0.102.1 production baseline from capabilities present only on the later `main` development snapshot. Deploying organizations should define which software revision is approved for project work and retain the exact version or commit in project records.

> [!WARNING] CleanroomX provides engineering screening, simulation, verification, and software/provenance evidence. It does not by itself establish ISO cleanroom certification, CFD validation, commissioning or TAB acceptance, manufacturer approval, physical measurement uncertainty, or regulatory acceptance.

## Revision history

| Revision | Date | Description |
| --- | --- | --- |
| A | 2026-09-30 | Rebuilt as an industry-oriented engineering user and operations manual with document control, role-based workflows, operating gates, evidence review, handoff procedures, troubleshooting, and reference appendices. |

## Approval record template

| Role | Name | Signature / approval reference | Date |
| --- | --- | --- | --- |
| Prepared by |  |  |  |
| Engineering review |  |  |  |
| QA / verification review |  |  |  |
| Approved for organizational use |  |  |  |

> [!NOTE] The approval table is a template. CleanroomX does not create or imply organizational approval. Use the document-control process required by your company, project, client, or regulator.

[[TOC]]

# PART I - PURPOSE, GOVERNANCE, AND FIRST USE

# 1. Product Purpose and Engineering Boundary

CleanroomX is a local Python engineering platform for cleanroom design, spatial planning, simulation, HVAC analysis, airflow and pressure-network studies, verification, uncertainty screening, BIM/IFC interoperability, reporting, and auditable numerical/provenance evidence.

The application is designed around one important architectural rule: the desktop GUI, command-line workflows, batch workflows, reports, and assurance layers use shared backend engineering services. Engineering equations are not intended to be independently reimplemented in GUI callbacks. This reduces the risk that two interfaces produce different answers for the same canonical input.

## 1.1 Capability families

| Family | Primary purpose |
| --- | --- |
| Spatial design | Synchronized 2D and 3D room layout, floors, dimensions, elevations, classifications, openings, equipment, devices, pressure visualization, and geometry validation. |
| Verification | Room and multi-room calculations for volume, ACH, particle criteria, observed pressure, pressure cascades, and aggregate completeness. |
| HVAC and thermal | Psychrometrics, sensible/latent/makeup loads, airflow balance, preliminary fan duty, and bounded thermal/psychrometric uncertainty. |
| Airflow networks | Duct losses, branch networks, looped networks, variable-friction networks, and related numerical provenance. |
| Fan studies | Supplied fan-curve operating point, speed/affinity studies, fan plus passive-network composition, and uncertainty. |
| Assurance and evidence | Consistency checks, dossiers, compliance rule packs, design assurance, snapshots, and ProofGraph evidence structures. |
| Project lifecycle | Strict JSON, atomic save, autosave/recovery, revision protection, bounded undo/redo, run history, and stale-evidence protection. |
| Handoff and automation | Portable reports, project bundles, deterministic batch execution, diagnostics, and CLI tooling. |

## 1.2 What CleanroomX does not decide for the engineer

CleanroomX does not invent project requirements. The engineer remains responsible for the authoritative values used as inputs, including room classifications, project-specific ACH targets, pressure-differential criteria, filter performance, leakage coefficients, duct roughness/friction assumptions, manufacturer fan data, weather/design conditions, measurement data, uncertainty information, and applicable standards or client criteria.

> [!STOP] A software `pass` must never be treated as proof that an external standard, client specification, commissioning requirement, or regulatory requirement has been satisfied unless the applicable criteria were explicitly and correctly represented in the evaluated input and the evidence has been reviewed by an authorized engineer.

## 1.3 Stable release versus development snapshot

The primary production baseline for this manual is v0.102.1. The current repository snapshot used to prepare the documentation contains later features that are not part of that tagged stable release. Those capabilities are marked as development snapshot features when discussed.

| Capability | v0.102.1 baseline | Later `main` snapshot |
| --- | --- | --- |
| Desktop GUI, 2D/3D spatial workspace, persistence, recovery, revisions, run history | Available | Available |
| Room/project verification, HVAC, thermal, duct, loop, fan and uncertainty workflows | Available | Available |
| Pressure/leakage network | Not part of tagged baseline | Available on `main` snapshot |
| Design foundation / pressure design consistency | Not part of tagged baseline | Available on `main` snapshot |
| Compliance rule packs / design assurance | Not part of tagged baseline | Available on `main` snapshot |
| ProofGraph evidence model | Not part of tagged baseline | Available on `main` snapshot |
| Newer IFC hardening and provenance enhancements | Baseline IFC support varies by release point | Additional hardening on `main` snapshot |

> [!MAIN] Development snapshot features should be treated as release-controlled software in your organization. Pin the exact commit, run the required verification gate, and document approval before using them for project decisions.

# 2. Roles and Responsibilities

Industry use improves when responsibilities are separated. One person may perform multiple roles on a small project, but the review intent should remain explicit.

| Role | Typical responsibilities in CleanroomX |
| --- | --- |
| Project / design engineer | Owns requirements, geometry, airflow assumptions, analysis inputs, engineering interpretation, and disposition of warnings. |
| HVAC / mechanical specialist | Reviews psychrometrics, loads, airflow balance, duct/network assumptions, fan data, and operating-point conclusions. |
| BIM coordinator | Controls IFC source revision, semantic mapping, re-import review, GlobalId identity, and geometry handoff. |
| Independent checker / reviewer | Confirms input provenance, units, acceptance criteria, result freshness, convergence, evidence completeness, and limitations. |
| QA / verification lead | Defines approved software revision, required records, release evidence, retention, and change-control expectations. |
| Application maintainer | Installs approved builds, confirms readiness, controls plugins, and preserves validated deployment records. |

## 2.1 Minimum separation for a released engineering result

For significant project decisions, the recommended pattern is:

1. The design engineer prepares the input and performs the analysis.
2. A second competent reviewer checks the source data, units, model assumptions, solver status, and acceptance criteria.
3. The project lead or responsible engineer approves use of the result in downstream design documents.
4. The issued record includes the CleanroomX version or commit, project revision, analysis identity, and report or bundle evidence.

> [!TIP] Treat the exported CleanroomX evidence as a traceable engineering calculation record, not as a substitute for a checking process.

# 3. Deployment Readiness and First Launch

## 3.1 Supported runtime

The stable package supports Python 3.11, 3.12, and 3.13. The base package declares no mandatory third-party Python runtime dependency. Tk support is required for the desktop GUI. Native IFC reading is optional and uses the BIM extra.

## 3.2 Windows repository checkout

```text
cd C:\CleanroomX
.\start-cleanroomx.ps1

# Command Prompt / Explorer-compatible launcher
start-cleanroomx.cmd

# Headless readiness check
.\start-cleanroomx.ps1 --check
```

The repository launcher prefers `.venv\Scripts\python.exe` when present, uses the repository `src` tree, and avoids PATH ambiguity from an older installed package.

## 3.3 Normal Python installation

```text
python -m venv .venv
python -m pip install -e .
cleanroomx-gui --check
cleanroomx-gui --demo
```

For development and verification work:

```text
python -m pip install -e .[dev]
python -m pytest -q
```

For native IFC support:

```text
python -m pip install "cleanroomx[bim]"
```

## 3.4 Deployment verification record

Before accepting a workstation for controlled engineering use, record at least:

| Check | Command / evidence | Acceptance |
| --- | --- | --- |
| Python version | `python --version` | Approved 3.11, 3.12, or 3.13 runtime |
| CleanroomX identity | package/repository version record | Matches approved release or commit |
| Registry readiness | `cleanroomx-gui --check` | Completes successfully |
| GUI launch | `cleanroomx-gui --demo` or Windows launcher | Application opens and demo loads |
| Optional BIM dependency | `cleanroomx-ifc --help` or representative import test | Required only when IFC workflow is approved for use |
| Verification suite | CI or local test evidence, according to organizational process | Required evidence retained |

> [!CONTROL] Do not proceed with normal project work when `cleanroomx-gui --check` fails. Treat this as an application wiring, installation, or source-state readiness failure.

## 3.5 First 20-minute operator familiarization

1. Launch the bundled demo.
2. Open the Design 2D + 3D workspace and inspect rooms and devices.
3. Select an existing analysis and use Validate before Run.
4. Inspect normalized result JSON, diagnostics/provenance, and the report view.
5. Make a harmless input change and confirm the previous result becomes stale.
6. Rerun the analysis and confirm a fresh result is produced.
7. Export a report to a temporary folder and inspect the output.
8. Close without modifying the original demo if the session is only training.

# 4. Standard Project Lifecycle

A professional workflow should use explicit gates rather than treating the Run button as the entire process.

| Gate | Operator action | Required evidence | Stop condition |
| --- | --- | --- | --- |
| G0 - Baseline | Confirm approved CleanroomX version/commit and project source revision | Version, commit/tag, project path/revision | Software or source identity is uncertain |
| G1 - Inputs | Enter or import geometry, engineering data, criteria, and references | Source notes, units, provenance, controlled files | Missing or ambiguous required source data |
| G2 - Validate | Use canonical parser/validation path | Successful validation or resolved findings | Invalid JSON, unsupported model, missing required data |
| G3 - Execute | Run the selected workflow | Completed fresh result with solver/provenance status | Non-convergence, dependency change, abandoned worker, execution error |
| G4 - Technical review | Check equations/model intent, assumptions, limits, status and completeness | Review notes / checker sign-off | Result is stale, incomplete, unchecked, or inconsistent with project intent |
| G5 - Cross-check | Run diagnostics/consistency/assurance as applicable | Diagnostics and related evidence | Conflicts, warnings without disposition, or unsupported acceptance claim |
| G6 - Issue | Export report, bundle, or snapshot | Issued file set with version and revision | Export freshness or integrity check fails |
| G7 - Archive | Preserve source project, referenced files, report, and approval record | Controlled project record | Missing source files or unverifiable handoff |

## 4.1 Recommended file naming convention

CleanroomX does not require a specific naming convention. A project organization may adopt a convention such as:

```text
PROJECT-AREA-REV03.cleanroomx.json
PROJECT-AREA-REV03_analysis-verification_report.html
PROJECT-AREA-REV03_handoff.cleanroomx.zip
```

Include a project revision that your document-control system understands. Do not rely on filenames alone; CleanroomX also records internal identity and hashes where supported.

## 4.2 When to rerun

Rerun an analysis when any input that affects the calculation changes. CleanroomX actively protects against stale evidence by binding completed results to the canonical SHA-256 identity of the submitted analysis input. File-backed workflows also fingerprint referenced dependencies.

> [!CONTROL] If a result disappears after an input edit, this is expected stale-result protection. Validate the revised input and run again. Do not copy values from the old result into a new report.

# PART II - DESKTOP AND PROJECT OPERATIONS

# 5. Desktop GUI Operating Procedure

## 5.1 Normal operator sequence

1. Create a new project or open a `.cleanroomx.json` project.
2. Add an analysis from the application catalog or select an existing analysis.
3. Edit or import the strict JSON object used by that workflow.
4. Select Validate to run the real backend parser and validation path without executing the engineering calculation.
5. Select Run to execute the backend workflow in a worker thread.
6. Review normalized result JSON, diagnostics/provenance, report output, and available plots.
7. Resolve warnings or unchecked criteria according to project rules.
8. Export only while the result is fresh.
9. Save the project using the normal guarded save path.

## 5.2 Run ownership and Abandon

The Abandon action suppresses the pending result but does not forcibly terminate the Python worker. The application maintains exclusive execution ownership until the worker exits. This prevents a second run from overlapping the abandoned computation.

> [!WARNING] Do not assume Abandon is an emergency thread kill. Wait for the application to report that the worker has finished before starting conflicting work.

## 5.3 Strict JSON input boundary

CleanroomX intentionally rejects permissive JSON constructs that could hide an engineering input error. Examples include malformed JSON, duplicate object keys at strict ingestion boundaries, and non-finite constants such as `NaN` and `Infinity`.

A valid engineering input should be explicit, finite, unit-consistent, and traceable to its source.

## 5.4 Cached results and freshness

Before restoring a cached result, accepting a background run, or exporting a result/report, CleanroomX compares the recorded input identity with the current analysis kind and input. A mismatch invalidates the cached result.

For file-backed workflows such as consistency and dossiers, referenced files are fingerprinted before and after the run. A changing or unstable dependency causes the result to be discarded rather than publishing mixed-revision evidence.

# 6. Project Files, Persistence, Recovery, and Revisions

## 6.1 Project document

Desktop projects use schema `cleanroomx.project`, schema version 1. The document contains project metadata, analyses, an optional active analysis identifier, and optional spatial metadata.

```text
{
  "schema": "cleanroomx.project",
  "schema_version": 1,
  "application_version": "0.102.1",
  "project": {"name": "My Cleanroom", "metadata": {}},
  "analyses": [
    {"id": "verification", "name": "Facility verification",
     "kind": "project_verification", "input": {...}}
  ],
  "active_analysis_id": "verification"
}
```

## 6.2 Save behavior

Project saves are validated and use atomic temporary-file replacement. When a saved project is opened, CleanroomX records a content revision. A normal Save is guarded so that an external edit, deletion, or replacement of the project file is not silently overwritten.

If the project changed externally, use one of these controlled options:

- Save Project As to preserve the current in-memory work under a new file; or
- reopen the newer disk revision and intentionally reapply required changes.

> [!STOP] Do not bypass an external-change save block by manually replacing the project file. The block exists to protect a newer source revision.

## 6.3 Legacy migration

Supported legacy single-analysis shapes are migrated in memory. A migrated legacy file opens as an unsaved converted copy. The first new save must be Save Project As to a different path. CleanroomX intentionally does not create a reverse migration back into the older format.

## 6.4 Autosave and recovery

Recovery autosaves are separate from explicit project files. They do not overwrite the open `.cleanroomx.json` source. Recovery artifacts include project state, raw editor draft, application version, timestamp, project identity, and source-file fingerprint evidence.

At startup, the Recovery Center can inspect available recovery state. Restore as Unsaved Copy preserves the original project and requires a new Save As destination.

> [!CONTROL] Recovery is a resilience mechanism, not a substitute for project backup, document control, or revision management.

## 6.5 Undo/Redo and run history

Project-wide transactional Undo/Redo applies to design edits. Persistent run-history evidence and camera/view state are not treated as ordinary design edits. Completed runs are retained with input/provenance identity according to the application's run-history rules.

# 7. 2D and 3D Spatial Design

The 2D editor and 3D viewer share one canonical spatial model. There is no independent 3D geometry copy.

## 7.1 Spatial objects

| Object | Stored information |
| --- | --- |
| Floor | Stable ID, name, elevation, default ceiling height, metric units |
| Room | Stable ID, X/Y, length, width, height, floor elevation, optional pressure, classification, analysis-room link |
| Device/opening | Stable ID, type, room assignment, coordinates, dimensions, orientation; wall openings may include wall side and swing |
| View | 2D/3D zoom and pan, azimuth/elevation, snap and visibility flags |
| Sync baseline | Analysis identity, room mapping identity, and last synchronized dimensions |

## 7.2 2D operations

The workspace supports room creation, selection, move, resize, duplicate, delete, and property editing. Devices and openings can include doors, windows, generic openings, supply, return, exhaust, FFUs, equipment, sensors, and transfer openings.

A room move also moves devices assigned to that room. Room and device duplication generates new stable IDs. A full drag gesture is treated as one undo/redo transaction, and no-op drag releases are suppressed so they do not create unnecessary history or autosave changes.

## 7.3 3D operations

The pure-Tk 3D view projects the same canonical spatial model. It supports orbit, zoom, pan, reset, and fit-to-view operations. Fit derives the view from actual room floor/ceiling corners, including elevated rooms.

## 7.4 Spatial integrity checks

Spatial validation detects conditions such as:

- non-finite or non-positive dimensions;
- duplicate stable IDs or room names;
- overlapping room footprints;
- dangling room references and orphan devices;
- devices outside assigned rooms or above valid elevation;
- unsupported device types or malformed view flags.

> [!WARNING] Passing spatial validation means the internal model is geometrically and structurally consistent. It does not establish airflow performance, cleanroom classification, fire/life-safety compliance, or constructability.

# 8. Spatial-Engineering Synchronization

Spatial geometry and engineering analysis inputs are deliberately separated. Synchronization is explicit rather than automatic.

## 8.1 Push and Pull

Use Push to analysis when spatial geometry is authoritative. Use Pull from analysis when engineering room geometry is authoritative. For room and project verification workflows, synchronization is dimension-focused and uses explicit room mappings.

Pull preserves the spatial X/Y placement. Engineering evidence such as a solved pressure is not silently written into geometry. Fresh verification pressure may be visualized without becoming part of the canonical spatial geometry state.

## 8.2 Synchronization states

| State | Meaning |
| --- | --- |
| synchronized | Mapped room dimensions match the persisted synchronization baseline. |
| geometry newer | The spatial dimensions changed since the last synchronized baseline. |
| engineering newer | The engineering dimensions changed since the last synchronized baseline. |
| conflicting | Both sides differ or provenance is insufficient to prove which side is newer. |
| unmapped | No valid explicit room mapping exists. |

> [!CONTROL] Resolve conflicting and unmapped states before issuing geometry-dependent engineering results. Synchronization is preflighted before mutation so an invalid later mapping cannot intentionally leave a partial update.

# PART III - ENGINEERING ANALYSIS WORKFLOWS

# 9. Room and Project Verification

## 9.1 Room volume and ACH

Room volume:

```text
V = length * width * height
```

Nominal supply air changes per hour:

```text
ACH = supply_airflow_m3_h / V
```

The calculation uses geometric room volume and the supplied airflow. The engineer is responsible for whether the supplied airflow and room volume are appropriate for the project criterion being checked.

## 9.2 Multi-room pressure cascade

A project can include explicit pressure-cascade relationships. CleanroomX evaluates supplied observations and criteria; it does not fabricate a missing room pressure.

```text
"pressure_cascade": [
  {"higher_pressure_room": "Process",
   "lower_pressure_room": "Preparation",
   "min_delta_pa": 10}
]
```

## 9.3 Aggregate verification states

| Status | Meaning |
| --- | --- |
| fail | At least one evaluated finding fails. |
| pass_with_unchecked | No evaluated finding fails, but at least one configured criterion remains unchecked. |
| pass | Every included finding is evaluated and passing. |
| not_checked | Nothing in the aggregate was evaluated. |

> [!CONTROL] Use `status` together with completeness. A no-failure boolean alone is not sufficient evidence that every required check was performed.

# 10. Particle Decay and Recovery

## 10.1 First-order screening model

Particle concentration decay:

```text
C(t) = C0 * exp(-(ACH/60) * eta * t)
```

Recovery time to a target concentration:

```text
t = ln(C0 / Ctarget) / ((ACH/60) * eta)
```

where `t` is in minutes when ACH is in 1/h and `eta` is the effective single-pass removal fraction.

The CLI includes direct screening commands:

```text
cleanroomx decay --initial 1000000 --ach 30 --minutes 10 --efficiency 1.0
cleanroomx recovery --initial 1000000 --target 100000 --ach 30 --efficiency 1.0
```

## 10.2 Observed recovery qualification

The dedicated recovery-test workflow can evaluate measured time-series samples against a target concentration and optional maximum recovery time. Instrument identity, sample location, occupancy state, and provenance can remain visible in the result/report.

> [!WARNING] The simple decay equation is not CFD. It does not model active particle sources, deposition, leakage, imperfect mixing, local recirculation, or detailed room-scale velocity fields.

# 11. Psychrometrics, Thermal, and HVAC

## 11.1 Steady room airflow balance

```text
net_surplus = supply + transfer_in - return - exhaust - transfer_out
surplus_margin = net_surplus - minimum_required_surplus
```

A positive surplus represents airflow available for exfiltration or another unmodeled outflow path. A negative result implies infiltration or another unmodeled inflow is required to close the balance.

## 11.2 Preliminary fan duty

```text
P_static = P_duct + P_coil + P_terminal_filter + P_other
Q_s = airflow_m3_h / 3600
air_power_W = Q_s * P_static
shaft_power_W = air_power_W / fan_efficiency
electrical_input_W = shaft_power_W / motor_efficiency
```

> [!WARNING] This is preliminary steady-state sizing. System effect, dirty-filter allowance, VFD/control losses, altitude correction, acoustic limits, motor service factor, and final manufacturer selection are not automatically inferred.

## 11.3 Thermal and psychrometric uncertainty

The bounded uncertainty workflows evaluate endpoint combinations of configured uncertain inputs and report result intervals. Capacity decisions distinguish pass, fail, indeterminate, and not-checked conditions rather than converting an overlapping uncertainty interval into a false pass.

> [!CONTROL] An `indeterminate` result means the evaluated interval crosses the decision boundary. It requires engineering disposition; it is not equivalent to pass.

# 12. Duct, Branch, and Looped Airflow Networks

CleanroomX includes duct pressure-loss analysis, passive parallel/branch solving, fixed-resistance loop solving, and variable-friction loop workflows.

## 12.1 Duct-loss review points

Before accepting a duct result, verify:

- geometry and cross-section units;
- airflow and density assumptions;
- friction factor or roughness method used by the selected workflow;
- local-loss coefficients and their source;
- equipment pressure drops entered separately from duct friction;
- critical-path selection;
- whether the result represents clean or dirty filter condition as required by the project.

## 12.2 Network convergence

Loop and nonlinear network workflows may fail to converge when the graph, boundary conditions, or numerical assumptions are invalid or ill-conditioned.

> [!STOP] Non-convergence must never be reported as a solved state. Review graph connectivity, balanced node injections, positive resistances, boundary conditions, and numerical controls before rerunning.

# 13. Fan Curves, Operating Point, Speed Studies, and Network Composition

Fan workflows use supplied fan data and system/network calculations to locate an operating point within the supported data range.

## 13.1 No extrapolation boundary

When the supplied fan and system curves do not cross within the supplied range, the workflow reports that no supported intersection exists rather than extrapolating a solution.

> [!CONTROL] A `no_intersection_in_supplied_range` result means the engineering data do not support an operating point in the supplied range. Extend or replace the manufacturer curve only from an authorized source; do not invent points to force an intersection.

## 13.2 Speed studies

Speed studies use the implemented affinity-law relationships and preserve numerical provenance around the supplied curve and selected operating state. Review whether the equipment and control system are permitted to operate across the requested speed range.

## 13.3 Fan plus network workflows

CleanroomX can compose a fan with passive networks, looped networks, variable-friction networks, and uncertainty studies. Treat the composed result as a coupled engineering calculation: changing either the fan data or the network model invalidates the operating state.

# 14. Pressure / Leakage Network

> [!MAIN] The room pressure/leakage network is documented from the later `main` snapshot and is not part of the tagged v0.102.1 production baseline. Use only under your approved development-snapshot procedure.

The pressure-network workflow solves room/node pressures against fixed references, mechanical injections/extractions, and configured leakage paths. Power-law leakage relationships require explicit coefficients and exponents supplied by the project engineer.

A representative single-path relationship is:

```text
Q = C * (deltaP)^n
```

For signed networks the implementation handles flow direction according to the configured pressure difference and path model. The user must provide realistic leakage parameters and a physically meaningful connected network.

## 14.1 Review checklist

- Every network component has a stable identity.
- At least one valid fixed-pressure reference or equivalent boundary is present as required by the model.
- Mechanical injection/extraction is intentionally defined.
- Leakage coefficients, exponents, areas, and offsets are traceable to project assumptions or measurements.
- Solver convergence is confirmed.
- Calculated pressure differences are compared to explicit project targets through the appropriate consistency workflow when needed.

# 15. Uncertainty, Qualification, and Numerical Precision

CleanroomX uncertainty workflows are deterministic engineering screening tools. They are not a substitute for a full statistical uncertainty analysis unless the configured model and organizational method establish that equivalence.

## 15.1 Presentation versus calculation precision

The software keeps canonical calculation state at full precision and rounds only presentation fields where designed. This is important for coupled workflows because a value displayed to a few decimals should not become the internal basis for a subsequent calculation.

## 15.2 Measurement uncertainty

If a decision depends on measured data, uncertainty information must come from the measurement system, calibration, sampling method, or approved engineering procedure. CleanroomX does not manufacture an uncertainty percentage when none has been supplied.

> [!WARNING] Software numerical precision and physical measurement uncertainty are different concepts. A numerically stable result does not prove that the field measurement or input assumption is accurate.

# PART IV - ASSURANCE, EVIDENCE, BIM, AND HANDOFF

# 16. Design Foundation, Consistency, and Design Assurance

> [!MAIN] Design foundation, pressure-design consistency, compliance rule packs, and design-assurance orchestration are later `main` snapshot features. They are not part of the tagged v0.102.1 baseline.

The design-assurance workflow is read-only orchestration over existing evidence-producing services. It does not introduce a second HVAC solver or invent a standards limit.

A typical assurance package can combine:

1. canonical design-consistency evidence;
2. optional explicit pressure-design consistency; and
3. one or more versioned compliance rule-pack evaluations.

## 16.1 Compliance rule-pack policy

Rule packs record explicit identity, version, source/reference, evidence paths, evaluation status, and a canonical SHA-256 digest. They do not grant authority to copyrighted or proprietary requirements.

> [!CONTROL] Criteria must come from authorized, public, licensed, or user-entered project sources. CleanroomX does not ship proprietary standards clauses or infer universal cleanroom limits.

## 16.2 Assurance snapshots

Design-assurance snapshots are intended to freeze and independently verify evidence identity. Use them to preserve the exact source bytes, normalized result, traceability digests, and replay information supported by the workflow.

A typical command sequence is:

```text
cleanroomx-assurance-snapshot create examples/design_assurance_demo.json design_assurance.snapshot.json
cleanroomx-assurance-snapshot verify design_assurance.snapshot.json
```

# 17. ProofGraph Evidence Model

> [!MAIN] ProofGraph schema version 1 is a later `main` snapshot evidence foundation and is not part of the tagged v0.102.1 production baseline.

ProofGraph is a GUI-independent evidence and traceability model. It is not a second engineering solver.

## 17.1 Core evidence objects

The model includes requirements, evidence sources, evidence records, design/calculation/simulation/commissioning/operational evidence layers, provenance records, confidence records, compliance checks, findings, verdicts, corrective actions, verification runs, and the ProofGraph container.

Cross-record references fail closed. Dangling references are rejected. Evidence provenance must remain acyclic. Reusing a provenance record ID ambiguously is rejected. Explicit project identities within one graph must agree.

## 17.2 Verdict states

| State | Meaning |
| --- | --- |
| pass | Requirement/check is supported by the required evidence and evaluated as passing. |
| warning | Review attention is required but the condition is not represented as a verified fail. |
| fail | Evaluated evidence does not satisfy the configured requirement. |
| unknown | Evidence or provenance is insufficient for a verified verdict. |
| indeterminate | Canonical analysis was evaluated but the result interval overlaps the decision boundary. |
| not_checked | The known requirement/check was not evaluated. |

A PASS finding must be evidence-backed. Missing evidence cannot be serialized as a successful compliance result.

## 17.3 Corrective actions

ProofGraph corrective actions retain `requires_approval=true`. The evidence foundation does not automatically apply an engineering remediation.

> [!CONTROL] Keep requirement, evidence, finding, verdict, and corrective-action identities traceable. Do not edit exported evidence files manually to manufacture a different verdict.

# 18. BIM / IFC Interoperability

CleanroomX includes an optional IFC semantic bridge separated from the engineering solvers. It converts supported IFC spaces and selected building-services/equipment semantics into the canonical CleanroomX spatial model and records source provenance.

## 18.1 Supported semantic mapping

The documented snapshot includes mapping for `IfcSpace`, `IfcDoor`, `IfcWindow`, `IfcAirTerminal` with explicit supply/return/exhaust semantics, generic flow terminals as equipment, sensors, selected flow controllers and unitary equipment, fans, pumps, and furnishings as equipment.

The importer uses IFC units, placement transforms, storey identity, GlobalId identity, and explicit CleanroomX-owned space properties where configured. It avoids guessing an airflow role from ambiguous generic terminal semantics.

## 18.2 Native IFC installation

```text
python -m pip install "cleanroomx[bim]"
```

## 18.3 CLI workflow

```text
cleanroomx-ifc import project.cleanroomx.json facility.ifc
cleanroomx-ifc plan project.cleanroomx.json facility-v2.ifc
cleanroomx-ifc reimport project.cleanroomx.json facility-v2.ifc
```

Initial import establishes identity. Plan is read-only. Reimport applies only a conflict-free candidate under the documented guards.

## 18.4 Desktop workflow

The BIM menu provides initial import, review re-import, and apply re-import operations. The review presents IFC `GlobalId`, mapped CleanroomX spatial ID, planned action, and whether local or source changes diverged from the prior baseline.

> [!CONTROL] A two-sided divergent edit must be resolved rather than silently choosing the local or IFC version.

## 18.5 Source stability and resource boundary

The documented `main` snapshot limits native IFC sources to 512 MiB and fingerprints source bytes around semantic extraction. Desktop review adds a second review-time stability boundary before mutation.

> [!WARNING] IFC import fidelity is intentionally conservative. Unsupported arbitrary-angle, tilted, reflected, skewed, or otherwise non-representable room geometry may fail closed rather than being approximated.

# 19. Reporting, Project Bundles, Batch Automation, and Diagnostics

## 19.1 Reports

Use reports only from fresh completed results. Portable HTML reports are intended to preserve exact input, result, and provenance in a reviewer-friendly file. Review the exported file before issuing it downstream.

## 19.2 Project bundles

Portable project bundles collect a project and referenced external dependencies into an integrity-checked handoff artifact. Bundle inspection rejects unsafe archive paths, duplicate or undeclared members, unsupported/encrypted content, integrity mismatches, and resource-limit violations before extraction is published.

A recommended handoff sequence is:

1. Save the project and confirm required analyses are fresh.
2. Run project diagnostics.
3. Export the bundle.
4. Verify the bundle before sending it.
5. Transfer through the organization's approved channel.
6. On the receiving workstation, verify and extract to a new/empty directory.
7. Open the extracted project and confirm the software baseline.

## 19.3 Project diagnostics

```text
cleanroomx-project-check project.cleanroomx.json
```

Diagnostics is a read-only project/model health check. It checks software/model/provenance conditions, not external certification.

> [!WARNING] A diagnostics `pass` means the configured CleanroomX checks found no errors or warnings. It does not establish ISO/GMP compliance, cleanroom certification, commissioning acceptance, or manufacturer approval.

## 19.4 Deterministic batch execution

Project batch execution is appropriate for repeatable automation when the project revision and analysis selection are controlled. Preserve batch output together with the exact source project and application version.

# PART V - DATA INTEGRITY, TROUBLESHOOTING, AND CHANGE CONTROL

# 20. Data Integrity and Traceability

## 20.1 Input identity

A released engineering result should be traceable to:

- CleanroomX version or exact commit;
- project file identity and revision;
- analysis ID and kind;
- canonical analysis input;
- external dependency hashes where applicable;
- execution status and solver convergence;
- report or run-bundle identity;
- checker/reviewer disposition.

## 20.2 Strict ingestion

CleanroomX uses strict JSON and finite-number boundaries to reduce ambiguous or non-portable engineering state. Unknown future schema versions fail closed. Duplicate analysis IDs and invalid active-analysis references are rejected.

## 20.3 External dependencies

Consistency and dossier workflows may reference external engineering files. Relative paths resolve from project path context and are rebased when a project is intentionally saved to another directory. During execution, dependency fingerprints protect against source changes during the run.

## 20.4 Evidence retention

For an issued calculation, retain the minimum set required by your project procedure. A robust set normally includes:

- approved project file;
- referenced controlled input files;
- issued report or portable HTML report;
- diagnostics / assurance evidence as applicable;
- project bundle for handoff where used;
- software version or commit record;
- review/approval record.

> [!TIP] Preserve inputs and evidence; do not preserve only screenshots of a result. Screenshots are convenient for communication but weak for reproducibility and audit.

# 21. Troubleshooting and Failure Handling

| Symptom | Meaning / safe action |
| --- | --- |
| Python 3.11+ not found | Install an approved supported Python or create the project `.venv`. On Windows prefer the repository launcher. |
| `cleanroomx-gui --check` fails | Treat as application readiness failure. Correct installation/source state before normal GUI use. |
| GUI/Tk error | Confirm the Python build includes Tk. On Linux automation use a real display or Xvfb as documented. |
| Invalid JSON / duplicate key / NaN | Correct the input. Do not attempt permissive normalization around the strict engineering boundary. |
| Save blocked because project changed externally | Preserve the newer disk source. Use Save Project As for current work or reopen the disk revision. |
| Recovery shown at startup | Inspect differences. Restore as Unsaved Copy only when the recovery state is needed. |
| Result disappears after edit | Expected stale-result protection. Validate and rerun. |
| External dependency changed during run | Stabilize source files and rerun. Discard the invalid mixed-revision attempt. |
| Fan reports no supplied-range intersection | Supply valid manufacturer data or revise the system model. Do not extrapolate by guesswork. |
| Pressure network non-convergence | Review connectivity, fixed boundary, path parameters, balance, and solver conditions. |
| Loop solver non-convergence | Check graph connectivity, balanced injections, positive resistances, and numerical controls. |
| IFC import rejected | Review source size, semantic support, placement/containment, axis-aligned representability, and source stability. |
| IFC re-import conflict | Use the read-only plan/review to resolve divergent local/source edits before apply. |
| Bundle verification rejected | Do not extract. Review integrity, member paths, size limits, declared dependencies, and source stability. |
| ProofGraph parse rejected | Review strict schema fields, IDs, cross-references, provenance cycles/project IDs, PASS evidence requirements, and verification-run closure. |

## 21.1 Incident response for a questionable issued result

When an issued result may be wrong or based on the wrong revision:

1. Stop further reliance on the affected result.
2. Preserve the project, report, bundle, and referenced input files exactly as found.
3. Record the software version/commit and the suspected issue.
4. Reproduce the calculation in a controlled copy.
5. Determine whether the issue is input data, model selection, numerical behavior, software defect, or document-control failure.
6. Reissue only after technical review and approval.
7. If a software defect is confirmed, open a tracked defect and evaluate impact on other calculations made with the affected version.

# 22. Security, Deployment, Migration, and Rollback

CleanroomX is a local desktop/CLI engineering application. It is not a network service, authentication system, secret store, or hostile-code sandbox.

## 22.1 Operational security guidance

- Run with normal user privileges.
- Keep project files and reports under normal OS access controls.
- Do not store credentials, API keys, or unrelated secrets in project JSON.
- Treat installed analysis plugins as trusted executable Python packages.
- Back up source projects before migration or bulk editing.
- Review reports before incorporating them into controlled downstream documentation.

## 22.2 Archive safety

Portable bundles are treated as untrusted archives and are inspected before extraction. Do not bypass failed bundle verification with a generic unzip process when the bundle is intended to be trusted as a CleanroomX handoff artifact.

## 22.3 Rollback

For repository deployments, prefer a reviewed Git revert of the release-changing commit rather than rewriting shared history. Preserve affected projects and evidence, identify the last validated baseline, revert through normal review/CI, and regenerate derived reports using the selected validated application revision.

For migrated project formats, retain the archived original if the legacy representation may be required later.

# 23. Validation Status and Software Change Control

The v0.102.1 release closure records complete-suite validation on Python 3.11, 3.12, and 3.13 with 1008 passing tests at the final deterministic spatial-drag release gate. The recorded release evidence also includes Windows launcher smoke coverage, clean wheel build/install checks, installed Tk GUI smoke testing, synchronized 2D/3D regression coverage, autosave race regression coverage, and solver/provenance compatibility gates.

> [!CONTROL] Regression coverage is software verification evidence. It is not an independent engineering validation of every possible project model, a formal security audit, or a substitute for project-specific checking.

## 23.1 Change-control impact review

When upgrading CleanroomX for controlled work, evaluate:

- software version / commit change;
- project schema or migration behavior;
- solver equations, tolerances, root-selection or no-extrapolation rules;
- reporting or evidence schema changes;
- BIM semantic mapping changes;
- persistence/recovery behavior;
- CLI interface changes;
- test and release evidence for the new baseline;
- whether existing issued calculations require re-execution.

A documentation-only commit should still be recorded if the manual or project procedure is part of the controlled environment, even when engineering calculations are unchanged.

# PART VI - OPERATING CHECKLISTS AND REFERENCE

# 24. Standard Operating Checklists

## 24.1 New project checklist

| Check | Complete |
| --- | --- |
| Approved CleanroomX baseline confirmed | [ ] |
| Project code/name and revision assigned | [ ] |
| Controlled source files identified | [ ] |
| Room geometry and units verified | [ ] |
| Engineering criteria entered explicitly | [ ] |
| Spatial-engineering mapping reviewed | [ ] |
| Project saved to controlled working location | [ ] |
| Initial diagnostics completed if required by procedure | [ ] |

## 24.2 Pre-run checklist

| Check | Complete |
| --- | --- |
| Correct project revision open | [ ] |
| Correct analysis ID/kind selected | [ ] |
| Input source and units checked | [ ] |
| Required file dependencies are stable and accessible | [ ] |
| Validate passes | [ ] |
| Model limitations understood | [ ] |
| Required acceptance criteria are explicit | [ ] |

## 24.3 Result review checklist

| Check | Complete |
| --- | --- |
| Run completed without error | [ ] |
| Result is fresh for current input | [ ] |
| Solver converged where applicable | [ ] |
| No unsupported extrapolation occurred | [ ] |
| `pass_with_unchecked`, `unknown`, `indeterminate`, warnings, or not-checked states have documented disposition | [ ] |
| Input and result units are correct | [ ] |
| Result magnitude is physically reasonable | [ ] |
| Assumptions and limitations are documented | [ ] |
| Independent checker has reviewed the evidence | [ ] |

## 24.4 Handoff checklist

| Check | Complete |
| --- | --- |
| Project saved and revision identified | [ ] |
| Required analyses rerun and fresh | [ ] |
| Project diagnostics reviewed | [ ] |
| Report / HTML report exported and visually checked | [ ] |
| Project bundle exported and verified when dependencies exist | [ ] |
| Software baseline recorded in transmittal | [ ] |
| Recipient instructions include bundle verification and extraction to a new directory | [ ] |
| Approval/transmittal record retained | [ ] |

## 24.5 IFC re-import checklist

| Check | Complete |
| --- | --- |
| Correct IFC revision selected | [ ] |
| Initial source identity / SHA-256 reviewed | [ ] |
| Re-import plan reviewed before mutation | [ ] |
| GlobalId-to-CleanroomX identity changes understood | [ ] |
| Divergent local/source edits resolved | [ ] |
| Candidate source remained stable through apply | [ ] |
| Spatial model validated after apply | [ ] |
| Engineering analyses intentionally synchronized or left unchanged as required | [ ] |

# 25. Worked Engineering Examples

## 25.1 Example A - ACH and idealized recovery

Room dimensions: 6 m x 5 m x 3 m. Supply airflow: 2700 m3/h. Initial particle concentration: 1,000,000/m3. Target: 100,000/m3. Effective removal efficiency: 1.0.

```text
V = 6 * 5 * 3 = 90 m3
ACH = 2700 / 90 = 30 1/h

t = ln(1000000 / 100000) / (30/60)
  = ln(10) / 0.5
  = 4.60517 minutes
```

Interpretation: the mathematical result is the idealized well-mixed recovery screening value. Field qualification should use measured recovery data and the applicable test procedure.

## 25.2 Example B - rectangular duct and preliminary fan power

Assume a rectangular duct 0.8 m x 0.45 m carrying 5400 m3/h for 18 m. Use Darcy friction factor 0.02, air density 1.2 kg/m3, and local loss coefficient K=1.8. Add coil loss 180 Pa and other loss 90 Pa. Fan efficiency 0.68 and motor efficiency 0.92.

```text
Area A = 0.8 * 0.45 = 0.3600 m2
Q = 5400 / 3600 = 1.5000 m3/s
v = 1.5000 / 0.3600 = 4.1667 m/s
Hydraulic diameter Dh = 0.5760 m
Velocity pressure = 10.417 Pa
Friction loss = 6.510 Pa
Local loss = 18.750 Pa
Duct total = 25.260 Pa
Fan total static = 25.260 + 180 + 90 = 295.260 Pa
Air power = 1.5 * 295.260 = 442.89 W
Shaft power = 442.89 / 0.68 = 651.31 W
Electrical input = 651.31 / 0.92 = 707.95 W
```

Interpretation: the result is preliminary fan-duty screening. Final selection still requires approved manufacturer data, system-effect consideration, operating margin, dirty-filter condition where applicable, and project-specific requirements.

## 25.3 Example C - simple pressure/leakage relationship

> [!MAIN] This example uses the later `main` pressure-network capability.

A process node injects 540 m3/h = 0.15 m3/s. The corridor reference is 0 Pa. A linear leakage path uses `C = 0.01 m3/s/Pa` and `n = 1.0`.

```text
0.15 = 0.01 * deltaP

deltaP = 15 Pa
```

An explicit design-consistency mapping can compare the solved signed pressure difference to a +15 Pa project target. The target must come from the project requirement, not from the solver result.

## 25.4 Example D - controlled handoff

1. Open the approved project revision.
2. Confirm the analyses required for review are fresh.
3. Run `cleanroomx-project-check` and disposition findings.
4. Export `review.cleanroomx.zip` using the project-bundle workflow.
5. Verify the bundle before transmittal.
6. Export a portable HTML report for the specific completed analysis when a human-readable calculation record is required.
7. Record software baseline, project revision, report/bundle names, and checker approval in the transmittal.

# 26. Command-Line Reference

The installed package exposes these primary commands. Use `COMMAND --help` for the exact options supported by the installed build.

| Command | Purpose |
| --- | --- |
| `cleanroomx` | Core calculations including direct room/particle utilities exposed by the main CLI |
| `cleanroomx-gui` | Desktop application, demo, and headless registry readiness check |
| `cleanroomx-project-run` | Deterministic saved-project batch execution |
| `cleanroomx-project-bundle` | Portable project bundle export / verification / extraction workflow |
| `cleanroomx-project-check` | Read-only project diagnostics |
| `cleanroomx-ifc` | IFC import, plan, and re-import workflow |
| `cleanroomx-hvac` | HVAC / thermal / airflow / fan screening workflow |
| `cleanroomx-recovery-test` | Observed particle recovery qualification |
| `cleanroomx-uncertainty` | Room uncertainty workflow |
| `cleanroomx-qualification` | Qualification workflow |
| `cleanroomx-duct-flow` | Duct-network pressure-loss analysis |
| `cleanroomx-loop-flow` | Fixed-resistance looped airflow network |
| `cleanroomx-pressure-network` | Room pressure/leakage network on the documented `main` snapshot |
| `cleanroomx-loop-friction` | Variable-friction loop solver |
| `cleanroomx-thermal-uncertainty` | Bounded thermal/HVAC uncertainty |
| `cleanroomx-psychrometric-uncertainty` | Bounded psychrometric uncertainty |
| `cleanroomx-fan-curve` | Fan/system operating point |
| `cleanroomx-fan-uncertainty` | Fan/system bounded uncertainty |
| `cleanroomx-fan-speed` | Fan speed / affinity-law study |
| `cleanroomx-fan-duct` | Fan plus duct-network composition |
| `cleanroomx-fan-network` | Fan plus passive network |
| `cleanroomx-fan-loop` | Fan plus looped network |
| `cleanroomx-fan-loop-friction` | Fan plus variable-friction loop |
| `cleanroomx-fan-loop-friction-speed` | Speed study with nonlinear variable-friction loop |
| `cleanroomx-fan-loop-friction-uncertainty` | Uncertainty around nonlinear fan/variable-friction loop |
| `cleanroomx-fan-loop-uncertainty` | Fan/loop bounded uncertainty |
| `cleanroomx-fan-loop-speed` | Fan/loop speed study |
| `cleanroomx-damper-study` | Loop resistance-multiplier scenarios |
| `cleanroomx-dossier` | Engineering dossier composition |
| `cleanroomx-consistency` | Cross-module consistency checks |
| `cleanroomx-assurance-snapshot` | Create / verify design-assurance snapshots |

# 27. Status, Units, and Interpretation Reference

## 27.1 General result interpretation

| Term | Interpretation |
| --- | --- |
| pass | Configured criterion was evaluated and passed. |
| fail | Configured criterion was evaluated and failed. |
| warning | Review attention is required. The exact meaning is workflow-specific. |
| not_checked | Known criterion was not evaluated. |
| unknown | Available evidence is insufficient for a verified conclusion. |
| indeterminate | Evaluated interval overlaps the decision boundary. |
| fresh | Result identity still matches current analysis input and required dependency revisions. |
| stale | Current input/dependencies no longer match the completed run. Rerun is required. |

## 27.2 Common engineering units

| Quantity | Typical unit in CleanroomX workflows |
| --- | --- |
| Length / room dimensions | m |
| Area | m2 |
| Volume | m3 |
| Airflow | m3/h or m3/s according to the field/workflow |
| Pressure | Pa |
| ACH | 1/h |
| Temperature | degC where documented |
| Relative humidity | fraction or percent according to the explicit field contract |
| Power | W / kW in reports as documented |
| Particle concentration | concentration per m3 |

> [!CONTROL] Always follow the field-level unit contract shown by the workflow/schema. Do not infer units from a number alone.

# 28. Standards and Reference Sources

CleanroomX separates standards-defined classification from project engineering airflow and HVAC inputs. The repository does not bundle copyrighted standards text and does not infer a universal fixed ACH from an ISO cleanliness class.

Primary references identified by the project documentation include:

- ISO 14644-1:2015, Cleanrooms and associated controlled environments - Part 1: Classification of air cleanliness by particle concentration. [Official ISO page](https://www.iso.org/standard/53394.html)
- ISO 14644-3:2019, Cleanrooms and associated controlled environments - Part 3: Test methods. [Official ISO page](https://www.iso.org/standard/60598.html)
- ISO 14644-4:2022, Cleanrooms and associated controlled environments - Part 4: Design, construction and start-up. [Official ISO page](https://www.iso.org/standard/72379.html)
- ASHRAE Design Guide for Cleanrooms: Fundamentals, Systems, and Performance. [ASHRAE official page](https://www.ashrae.org/technical-resources/bookstore/ashrae-design-guide-for-cleanrooms)
- 2025 ASHRAE Handbook - Fundamentals, Chapter 1, Psychrometrics. [ASHRAE Handbook page](https://handbook.ashrae.org/Handbooks/F25/SI/F25_Ch01/F25_Ch01_si.aspx)
- JCGM 100:2008, Evaluation of measurement data - Guide to the expression of uncertainty in measurement. [BIPM/JCGM official page](https://www.bipm.org/en/doi/10.59161/JCGM100-2008E)
- JCGM 106:2012, Evaluation of measurement data - The role of measurement uncertainty in conformity assessment. [BIPM/JCGM official page](https://www.bipm.org/en/doi/10.59161/JCGM106-2012)
- NIST Technical Note 1297, Guidelines for Evaluating and Expressing the Uncertainty of NIST Measurement Results. [NIST official page](https://www.nist.gov/pml/nist-technical-note-1297)

> [!WARNING] Referencing a standard does not mean CleanroomX has encoded every clause or that a project is compliant. Use licensed standards and the approved project specification to define the criteria actually evaluated.