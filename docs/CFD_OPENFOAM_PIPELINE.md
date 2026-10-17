# CleanroomX external OpenFOAM CFD pipeline

This feature generates three 3D case directories for **OpenFOAM Foundation
v10** steady incompressible laminar flow, optionally executes the external
blockMesh/checkMesh/simpleFoam programs, and imports independently solved VTK
cell fields. It provides sampled-cell cross-section PNGs for reviewing velocity
and optional scalar concentration data.

The generated dictionaries use the Foundation v10 physicalProperties and
momentumTransport names. The fvSchemes file includes the viscous-stress
divergence term used by the v10 simpleFoam tutorial. These are version-specific
case-input checks; they do not replace running the generated case with the
target release.

## Desktop OpenFOAM workspace

The CleanroomX desktop application has an **OpenFOAM** tab for the supported
three-case workflow. Select a specification JSON and a new output directory to
generate the case bundle. The **Run Foundation v10** action requires an explicit
confirmation and launches the bundled CLI with the current Python interpreter.
Set an optional result directory to synchronize stable native fields during
the run; the supplied simulation ID groups the imported snapshots.

For an existing `foamToVTK` export, select its VTK directory, the generated
case bundle's `manifest.json`, a result directory, and a simulation ID, then
choose **Sync VTK once**. The command uses the normal stability checks. Repeat
the scan after the configured stability interval when the initial scan reports
pending files. On compact displays, the case settings scroll independently while
a small, scrollable command log stays visible. The live console keeps at most
4,000 lines and 500,000 characters, whichever cap comes first, so long solver
output cannot grow the GUI text widget without limit. CleanroomX retains the
complete session transcript in a temporary spool that spills to disk after 1 MB
while the workspace remains open. Use **Save full log…** to export it before
closing the workspace. If temporary storage fails, the GUI reports that
complete-log capture stopped.

**Verify case inputs** performs a read-only preflight over the generated bundle:
it checks the exact 24 manifest-bound input files, verifies their SHA-256
digests, rejects linked or oversized inputs, and reruns the boundary-geometry
and inlet-flow consistency audit for all three configurations. Hashes are
compared with the bundle's local unsigned manifest. The result does not run
OpenFOAM or establish solver convergence, grid independence, or physical
validation. **Preview result evidence** displays selected fields and raw-file
SHA-256 values without independently validating those hashes.

**Export ProofGraph…** reads the synchronized result manifests under the chosen
result store and simulation ID. It re-hashes each manifest, immutable receipt,
and referenced result asset before writing a standalone ProofGraph JSON file
and loading it into the application's viewer. A missing configuration is
represented as `not_checked`; a malformed manifest or mismatched asset hash
aborts export. A PASS verdict covers local hash-link consistency only. It does
not establish authenticity: no digital signature or external trusted digest is
checked, and the export does not reopen the original native source-field files
to re-hash their contents. Solver convergence and physical validation remain
`not_checked` / `BLOCKED`, even when solver metadata or VTK parity reports
success. **Load ProofGraph JSON** remains
available for persisted graphs created elsewhere.

The tab is a software workflow integration. It does not yet derive OpenFOAM
boundary geometry from the active CAD/IFC project or attach the standalone
export to project requirements. Scientific validation remains `BLOCKED`
pending independent cleanroom measurements, justified acceptance criteria, and
engineering review.

## Educational source and limits

The uploaded NANENG 523 Lab 1 CFD handout describes three single-pass airflow
layouts and qualitatively prefers the third. It does not supply reproducible
numerical geometry, mass-flow boundary conditions, mesh convergence data,
material properties, solver logs, contamination-source rate or acceptance
criteria. **None of these is invented by CleanroomX.** Example parameters are
SYNTHETIC functional smoke test values only.

Configuration 1 has central ceiling supply and low-wall exhaust;
Configuration 2 has distributed ceiling supply and low-wall exhaust;
Configuration 3 has distributed ceiling supply and a perforated-floor
effective exhaust boundary. The underfloor plenum and perforation hydraulics
are **not resolved**. No internal furniture/FFUs/obstacles are modeled.

## Install / generate / run

In Python 3.11+:

    pip install -e '.[cfd]'

Generate all three cases without OpenFOAM installed:

    cleanroomx-cfd-pipeline generate examples/cfd_openfoam_spec.example.json ./cfd_cases

Each case manifest includes an input-only boundary audit. It reads the
generated `blockMeshDict` face coordinates, derives the complete exterior-face
set from its hex blocks, and requires each exterior face exactly once across
the patches. Duplicate, omitted, internal, non-manifold, or unsupported block
faces are rejected. It recomputes inlet/outlet areas and
outward normals, checks the generated `U`/`p` patch-condition types, and
integrates the prescribed inlet velocity over the inlet faces against the
requested supply flow. The audit records the outlet solver flux as
`not_measured`, the flow balance as `not_measured`, and scientific validation
as `BLOCKED`. It does not establish that the example room, patch placement,
or requested flow matches a real cleanroom, and it does not replace reviewing
the solver's actual inlet/outlet `phi` after execution.

Inspect the resulting system, constant, and 0 field files. The manifest binds
each generated input using SHA-256; existing output directories are not
overwritten. Supply airflow is imposed by downward velocity determined from
each configuration's explicit inlet patch area.

Install OpenFOAM Foundation v10 on Linux/WSL and source its `etc/bashrc` so
`WM_PROJECT=OpenFOAM` and `WM_PROJECT_VERSION=10`; keep `blockMesh`,
`checkMesh`, and `simpleFoam` on PATH. The runner checks those environment
markers, then verifies each executable's log banner identifies
`https://openfoam.org`, Version 10, and one consistent build. It records the
resolved executable paths and build identifier. For `checkMesh`, it also
records a hash-bound structured diagnostic summary of mesh counts, cell types,
bounding box, areas, volumes, and the geometric checks printed by OpenFOAM.
The summary copies the tool's reported result but sets project acceptance to
`not_assessed_no_project_criteria`; it never applies invented quality limits.
The runner stops before `simpleFoam` if the Foundation v10 report is incomplete
or `checkMesh` reports failure. Other OpenFOAM distributions and releases are
rejected by this v10 case runner. Then opt in:

    cleanroomx-cfd-pipeline run ./cfd_cases --timeout-seconds 3600

The runner checks input hashes, recomputes the boundary audit from the bound
case files, returns those audit records with its execution receipt, uses no
shell and records solver logs. A zero
return code is **not CFD convergence**: inspect residuals, continuity,
boundary flux balance, turbulence/Reynolds applicability, mesh quality and
grid independence. Other OpenFOAM versions may require solver template
changes: v11+ Foundation uses foamRun solver modules.

| Distribution | Case generation | Solver runner / native-field synchronization | Evidence status |
| --- | --- | --- | --- |
| OpenFOAM Foundation v10 | Supported template | Supported with `blockMesh`, `checkMesh`, `simpleFoam`, `foamToVTK`, and Python VTK | The pinned workflow exercises the v10 path; execution and data integrity do not establish physical validation |
| Foundation v11+ | Not runtime-qualified | Unsupported; the runner expects the v10 `simpleFoam` workflow | Not verified |
| OpenCFD/OpenFOAM.com releases | Not runtime-qualified | Unsupported by this runner | Not verified |

The runner checks the distribution and version markers before launching tools.
Other releases need a separately tested compatibility adapter; a v10 marker
does not establish compatibility with another vendor.

See [OpenFOAM checkMesh diagnostics](OPENFOAM_CHECKMESH_DIAGNOSTICS.md) for the
receipt schema, parser behavior, and the distinction between reported
`checkMesh` checks and project-defined mesh acceptance.

The GitHub nine-case Foundation v10 workflow additionally requires
`foamToVTK`. After each successful `simpleFoam` run, it exports the latest
cell velocity `U`, kinematic-pressure `p`, and surface flux `phi` with ASCII
output, imports the cell dataset, and binds its hash and cell count to the
generated-input manifest. It then reopens and verifies all nine outputs before
uploading the evidence artifact.
This workflow export is a reproducibility and ingestion check; it is not part
of the standalone `run` command and does not establish CFD convergence,
mesh independence, or physical validation.

The separate bounded two-room pressure-probe and flux integration case is
documented in [Two-Room OpenFOAM Workflow](CFD_TWO_ROOM.md). Its synthetic 5 Pa
target is an engineering screen only and does not establish a project pressure
cascade requirement.

The nine-case v10 workflow compares exported cell velocity and kinematic
pressure with the native final-time OpenFOAM `U` and `p` fields. It uses the
`cellID` cell-data array
written by Foundation v10 `foamToVTK`: the upstream
[`internalWriter::writeCellIDs` implementation](https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/applications/utilities/postProcessing/dataConversion/foamToVTK/foamToVTK/internalWriter.C)
emits the original mesh cell index for every cell. CleanroomX requires a
complete, unique ID mapping and compares each U component and p scalar by that
ID; it does not infer cell correspondence from VTK array order. The U audit
requires cell-data `U`, so it cannot silently substitute point-to-cell
interpolation. The p audit requires a native `volScalarField` with kinematic-
pressure dimensions `[0 2 -2 0 0 0 0]` and a scalar cell-data `p` array.

Foundation v10's legacy VTK output declares these U and p arrays as `float`.
The parity receipt reports measured component/scalar errors and bounds them
using binary32 rounding plus half a last decimal place at the workflow's
six-digit ASCII precision. These tolerances describe field serialization only;
they are not CFD solver acceptance thresholds and provide no convergence or
physical validation evidence.

The workflow also requests `foamToVTK -surfaceFields` for the native
`surfaceScalarField phi`. In the pinned Foundation v10 implementation,
[`foamToVTK.C`](https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/applications/utilities/postProcessing/dataConversion/foamToVTK/foamToVTK.C)
converts each scalar flux to `phi` times the oriented unit face normal, and
[`writeSurfFields.C`](https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/applications/utilities/postProcessing/dataConversion/foamToVTK/foamToVTK/writeSurfFields.C)
serializes those values with the mesh face centres in face order. CleanroomX
reconstructs face centres and normals from the archived `polyMesh`, checks the
serialized centre sequence, and compares all three vector components within
the float32/ASCII bounds. This checks the v10 export representation for the
synthetic mesh family; it does not set a flow-balance criterion or establish
solver convergence or physical validity.

The Foundation v10 integration workflow makes a separate multi-time export
using `foamToVTK -time 50,100 -useTimeName`. It requires the utility log to
show exactly the requested `50` and `100` times in order, then compares the
exported internal U/p, inlet/outlet/walls U/p, and surface `phi` datasets with
the native fields in each matching time directory. The v2 sidecar receipt
binds the command log, source fields, and every selected-time VTK file by
SHA-256. The selected times avoid the baseline latest-time output at `150` and
cover two exact times from the synthetic three-output case. This does not
establish arbitrary time-range support, solver convergence, or physical
validation. The pinned upstream [`foamToVTK.C`](https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/applications/utilities/postProcessing/dataConversion/foamToVTK/foamToVTK.C)
registers comma-separated time ranges, iterates the selected time directories,
and uses `-useTimeName` to name each dataset from the solver time name.

## Incrementally synchronize VTK time results

`sync-vtk` incrementally imports `foamToVTK` volume datasets named
`<case>_<time>.vtk` or `.vtu` at the VTK root, as well as `internal.vtk` or
`internal.vtu` under numeric time directories. The source must be the
`foamToVTK` output tree; this command does not start OpenFOAM or run
`foamToVTK` itself. For an export tree at
`cfd_cases/configuration_1/VTK`, use the generated family `manifest.json` as
configuration provenance:

    cleanroomx-cfd-pipeline sync-vtk \
      ./cfd_cases/configuration_1/VTK ./cfd_results/configuration_1 \
      --simulation-id airflow-config-1-run-001 \
      --configuration-file ./cfd_cases/manifest.json \
      --interval-seconds 2 --stable-scans 2

The watcher stores restart state in `sync-state.json` and writes each accepted
snapshot atomically under `snapshots/`. The first observation remains pending;
the same size and modification time must be observed on a later scan. CleanroomX
then imports the VTK file through the existing bounded importer, checks the
source hash before and after parsing, and records simulation ID, raw
configuration SHA-256, solver time, file hash, mesh-cell count, and import
timestamps. Repeating the command resumes the existing state. `--once` performs
one scan and exits. A newly discovered file needs another scan after the
default two-second stability window; use `--stable-seconds` and
`--stable-scans` to configure that gate.

The watcher refuses a changed configuration or field map in an existing result
store, rejects conflicting exports for the same case and solver time, preserves
an accepted snapshot if its source is later modified, and enforces file-count,
scan-entry, source-byte, and output-record limits. Stable size/mtime observations
are a write-completion screen, not a guarantee from the solver; the importer
must also parse the dataset and the source hash must remain unchanged throughout
ingestion. The producing process should finish each `foamToVTK` write before
the watcher accepts it.

Every result always maps cell-data `U` to velocity in m/s. VTK exports do not
carry OpenFOAM field dimensions, so optional arrays require explicit semantic
and unit declarations through `--field-map-file`; those declarations and their
SHA-256 are recorded with each snapshot. The example
[`cfd_openfoam_field_map.example.json`](../examples/cfd_openfoam_field_map.example.json)
maps `p` to kinematic pressure (m^2/s^2) and defines optional turbulence
fields. An absent mapped array is recorded as unavailable; a malformed or
non-finite array is rejected. Array names alone do not identify physical
meaning: `T` is not automatically treated as temperature or contaminant
concentration. Use `--contaminant-array` only when the selected scalar has
known concentration semantics. Field mapping preserves the exported values;
it does not convert kinematic pressure to Pa without a supplied density or
convert other fields between units. Solver convergence and physical validation
remain separate gates.

Mapped-field means are volume-weighted and carry an explicit weighting label.
This field-summary change uses synchronization-state and snapshot schema v3.
Existing v1/v2 stores are refused rather than silently mixed with different
field semantics; start a new output store to import with the updated mapping.

## Synchronize native fields during `simpleFoam`

`sync-vtk` above imports a VTK tree that already exists. To let the case runner
watch native OpenFOAM time directories, export each stable time with
`foamToVTK`, compare the VTK values with the native fields, and store verified
snapshots while `simpleFoam` is still running, opt in with:

    cleanroomx-cfd-pipeline run ./cfd_cases \
      --sync-results ./cfd_sync_results \
      --simulation-id room-study-2026-01 \
      --sync-poll-interval-seconds 1

It monitors the three generated cases. A positive numeric time is eligible
after the configured settle polls see the same selected field set, file
identity, size, and modification time. The exporter works in an isolated
temporary case view, waits for `foamToVTK` to finish, checks that source fields
did not change during export, verifies U and any available p cell values
against native fields, and atomically publishes VTK assets, a receipt, and a resumable
manifest. It never replaces an accepted time after the source changes.

This direct path requires Foundation v10 and legacy ASCII VTK output. The
airflow mode requires ASCII native fields U and kinematic-pressure p. A
scalar-transport run requires both U and T because `scalarTransportFoam` does
not produce p; the watcher does not publish a scalar time until both files are
stable. Both modes import
configured optional volume fields (T, k, epsilon, omega, nut by default), and
surface flux phi when present. Standard optional fields are
checked against their OpenFOAM dimensions: k, epsilon, omega, and nut must use
their standard turbulence dimensions. T is treated as temperature only when
its native dimensions are kelvin. Foundation v10 `scalarTransportFoam` also
uses `T` for passive scalars, including dimensionless tracers; non-kelvin T is
retained with its native dimensions and is not mapped as temperature. Set
`--contaminant-field NAME` only when that field has verified concentration
semantics and units. A dimensionless tracer is not a physical concentration.
No solver output is synthesized when no new time is written. Records report
`DIAGNOSTIC_ONLY`; solver convergence, physical validation, and cleanroom
qualification remain blocked.

The native runtime-result manifest uses schema v2 to distinguish its explicit
temperature and contaminant semantics from earlier records. Existing v1 result
stores must be retained as historical evidence and a new output directory used
for this schema; the synchronizer refuses to relabel old snapshots in place.

For a separately launched solver, use `sync-case` with the same simulation ID
and output directory to resume its native-time watcher:

    cleanroomx-cfd-pipeline sync-case ./active_case ./cfd_sync_results \
      --simulation-id room-study-2026-01 \
      --solver-log simpleFoam.log \
      --max-runtime-seconds 3600

After seeing the terminal `End` marker, this watcher drains final stable
writes but reports `outputs_synced_process_status_unknown` because it cannot
inspect the solver process return code. `run --sync-results` records the real
return code and reports `results_synced` only when the process exits zero, the
log ends in `End`, and no unrecovered synchronization errors remain. Re-run
`sync-case` with the same case, ID, and output store after an interruption.
For a separate `scalarTransportFoam` case, `scalar-run --sync-results` runs the
solver under that watcher. Use `--field-map-file` to assign explicit meaning
and units to its dimensionless `T`; the example map records `normalized_tracer`
with units `1`, without labeling it temperature or physical concentration.
For a separately launched scalar solver, use:

    cleanroomx-cfd-pipeline sync-case ./scalar_case ./scalar_sync \
      --required-fields U T --optional-fields \
      --field-map-file examples/cfd_scalar_field_map.example.json \
      --solver-log scalarTransportFoam.log

Defaults are 256 MiB per field, 512 MiB per time snapshot, 2 GiB total output,
three retries per failed snapshot, and a 600-second `foamToVTK` timeout. The
integrated runner accepts `--sync-max-field-mib`,
`--sync-max-snapshot-mib`, `--sync-max-output-mib`, `--sync-max-retries`, and
`--sync-timeout-seconds`; `sync-case` has the corresponding `--max-*` options.
The polling interval is configurable from 0.1 to 60 seconds.

For a dimensionless passive tracer, the example
[`cfd_scalar_field_map.example.json`](../examples/cfd_scalar_field_map.example.json)
maps `T` to `normalized_tracer` (unit `1`). The scalar watcher records native
dimensions and native-to-VTK parity at each stable solver write. Physical
contaminant limits, measured source strengths, and concentration units must be
supplied separately before contaminant acceptance analysis.

Foundation v10 run 94 completed this `50,100` audit for all nine synthetic
cases. Its [multi-time report](OPENFOAM_V10_RUN_38872039438_MULTI_TIME_VTK_AUDIT.md)
records 18 case-time pairs and 108 passing internal, patch, and surface-flux
parity records. Independent replay matched all 72 generated-input hashes, 36
baseline stage-log hashes, the manifest and execution-receipt hashes, and all
153 selected-time file records. The artifact SHA-256 is
`fa5b85af0e8ed2470101747540f22808032ba1959c0f41548551b62a24f060a3`.
The results remain `DIAGNOSTIC_ONLY`; scientific validation remains `BLOCKED`.

Run 90 applied this audit to all nine generated cases. Its 54 internal-field, patch, and surface-flux parity records passed, including 13,608 patch faces. The [run 90 report](OPENFOAM_V10_RUN_38867911839_VTK_TIME_SELECTION.md) records the independent artifact-digest and file-hash replay. Residual and flow-balance screens remain diagnostic; scientific validation remains BLOCKED.

The independently rechecked run 58 U archive and per-case native/VTK hashes
are recorded in [the run 58 parity report](OPENFOAM_V10_RUN_38694132081_NATIVE_VTK_PARITY.md).
Run 61 extends that check to native final-time `U` and `p`; its artifact,
per-case errors, and independent digest checks are recorded in [the run 61
U/p parity report](OPENFOAM_V10_RUN_38768856636_NATIVE_U_P_VTK_PARITY.md).

Run 63 also checks the separate `inlet`, `outlet`, and `walls` patch surfaces.
It maps VTK faces to native boundary faces by serialized point geometry, checks
`patchID` and full face coverage, and compares patch U/p against native
boundary-field values. The workflow covers 27 patch datasets, 13,608 faces,
40,824 velocity components, and 13,608 pressure values; the independent
artifact recheck and per-patch errors are in [the run 63 patch-parity report](OPENFOAM_V10_RUN_38772855917_NATIVE_VTK_PATCH_PARITY.md).
This verifies only the current synthetic single-region family and its present
boundary-condition types; it does not add patch surfaces to volume-weighted
cleanroom metrics.

## Import actual CFD results (VTK/VTU)

Export solved fields with your OpenFOAM installation's foamToVTK utility,
or an equivalent CFD package that produces an unstructured grid. Prepare a
CleanroomX cfd-study v1 JSON with explicitly verified room dimensions,
source coordinates, design limits, fluxes and matched boundary conditions.

    cleanroomx-cfd-pipeline import-vtk study.json \
      --case-1 c1.vtu --case-2 c2.vtu --case-3 c3.vtu \
      --solver-name 'OpenFOAM v10' --output evaluated.json

Required field: three-component U in m/s, available at cell or point level.
Real cell volumes are computed from the VTK mesh. A scalar is never treated as
contamination by its name: pass `--contaminant-array CO2` only for a field known
to contain concentration values, and provide the project-specific concentration
limit and units in the study. Absolute temperature can be imported separately
with `--temperature-array T --temperature-units K`; the source values must be
kelvin. Its volume-weighted mean, minimum, maximum, and cell-volume coverage are
reported separately from contaminant metrics. Additional scalar/vector fields,
including turbulence quantities, can be declared through `--field-map-file`;
their semantics and units remain explicit metadata and are not inferred from
array names. SHA-256 hashes bind raw VTK sources. NaNs, invalid volumes or
concentrations, changed inputs and oversized sources fail. Missing
scalar/recirculation/flow evidence blocks a three-case winner. This feature
**does not solve scalar transport**.

## Compare visualized cell samples

    cleanroomx-cfd-pipeline plot \
      --case-1 c1.vtu --case-2 c2.vtu --case-3 c3.vtu \
      --field speed --axis y --position-m 1 --slab-thickness-m 0.25 \
      --output velocity-slab.png

For an explicitly selected absolute-temperature array in kelvin, use
`--field temperature --array-name T --units K`. For contaminant or another
mapped scalar, select `--field contaminant` or `--field scalar`, then provide
its array name and declared source units with `--array-name` and `--units`.

This displays cell-center samples inside a finite-thickness slab; it is not
an interpolated CFD contour or velocity streamline. The plot does not certify
CFD, ISO classification, or any regulatory qualification.

The Foundation v10 integration workflow runs this command on the final-time
coarse-grid datasets in the native runtime-sync store for configurations 1–3.
It uploads `airflow-speed-cross-section.png` and the JSON report with the solver,
synchronization, and VTK parity evidence. The plot step reads the synchronized
files directly and checks that each configuration contributes samples; it
does not promote the samples to CFD validation evidence.

For the exact-head Foundation v10 run that exercised solver execution, incremental synchronization, multi-time field parity, and this visualization, see the [run 38889697945 evidence report](OPENFOAM_V10_RUN_38889697945_RUNTIME_SYNC_VISUALIZATION_EVIDENCE.md).

The latest pinned Foundation v10 workflow, [run 38905424325](OPENFOAM_V10_RUN_38905424325_END_TO_END_EVIDENCE.md),
re-executed the nine-case airflow family, incremental native-field and VTK
synchronization, a real passive-tracer `scalarTransportFoam` case, and sampled
velocity visualization. Its artifact was independently checked by digest,
asset hashes, and native-to-VTK parity. The run verifies the reproducible
execution and ingestion path only; all residual screens remain outside the
documented tolerances and scientific validation remains blocked.

The later exact-head run 38894717248 repeated the nine-case Foundation v10
execution, multi-time export, incremental VTK synchronization, and visualization.
Its artifact digest, case counts, synchronization records, residual and flux
screens, and scientific limits are recorded in the [run 38894717248 evidence
report](OPENFOAM_V10_RUN_38894717248_EXECUTION_SYNC_EVIDENCE.md).

See the [Foundation v10 runtime-sync evidence report](OPENFOAM_V10_RUN_38888517187_RUNTIME_SYNC_EVIDENCE.md)
for the exact-head solver, field-parity, synchronization, visualization, and
validation-limit records.

## Engineering follow-on gates

A full physically validated CFD system needs real CAD/IFC boundary geometry,
diffusers, fan/filter and perforated-tile hydraulics, turbulence and buoyancy,
particle/scalar transport with true source terms, sensitivity/refinement
studies, solver residual/flux convergence, onsite measurements, full GUI
integration, dossier and ProofGraph evidence. The exporter is intentionally
bounded to 20,000 hexahedral cells for a reproducible first solver pipeline,
not as a declared mesh-accuracy target.

OpenFOAM references:
https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/tutorials/incompressible/simpleFoam/pitzDaily/constant/physicalProperties
https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/tutorials/incompressible/simpleFoam/pitzDaily/constant/momentumTransport
https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/tutorials/incompressible/simpleFoam/pitzDaily/system/fvSchemes
https://github.com/OpenFOAM/OpenFOAM-10/blob/89f925dc708d068f84f51e8317e3bebcda64f5cb/etc/bashrc
https://doc.cfd.direct/openfoam/user-guide-v10/turbulence
https://cpp.openfoam.org/v10/scalarTransportFoam_8C_source.html
