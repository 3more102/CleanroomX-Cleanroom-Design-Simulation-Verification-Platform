# Run a Studio room with OpenFOAM

The Studio and solver workspace now share one desktop application. A room study
copies the selected room's current dimensions and its declared verification
supply airflow into three alternative OpenFOAM Foundation v10 cases. Run launches
real `blockMesh`, `checkMesh`, `simpleFoam` and `foamToVTK` processes. Imported
pressure, velocity and flux values come from their output files.

## Desktop workflow

1. Install the application with `python -m pip install -e ".[cfd]"` and launch
   `cleanroomx-gui --demo`, or open your own project.
2. Select a room or an assigned device and choose **CFD / simulation…**.
3. Choose the solver connection and press **Check runtime**. Review the console
   report, including executable paths, release, VTK and launch availability.
4. Review supply airflow, mesh counts, iteration limit and the runs folder.
   Missing, conflicting or ambiguously linked verification flow stays empty and requires a value.
   Two Studio rooms linked to the same engineering-room name never silently share
   an automatically selected supply flow; enter and review a value explicitly.
5. Press **Run room study**. If the selected room's geometry, engineering
   identity or verification airflow changed since opening the solver panel,
   CleanroomX refreshes the inputs and requires another Run action after
   review. Unrelated project-note edits do not force repeated review.
   The top Run button also starts this workflow while
   the OpenFOAM tab is active. Live progress reads the actual stage logs and
   displays recorded solver time and residuals; it is not convergence percentage. Fatal log diagnostics and invalid/non-finite
residual values are surfaced across all cases, even if subsequent logs exist;
affected stages are not counted as finished by the indicator. Verified receipts
and the process exit status remain authoritative for success.
6. The result explorer opens automatically after successful synchronization.
   Select field history, residuals, boundary flow balance, whole-domain supply ACH,
   spatial cell samples or region statistics. **Export report + data…** retains
   the selected graphs, raw graph values, sources and hashes.

Each run uses a new directory. It retains `project-input.json`,
`specification.json`, `room-study.json`, 24 generated case inputs, solver logs,
`execution-receipt.json`, native fields and synchronized VTK/receipt assets.
Editing the project afterwards does not rewrite a previous run's inputs.
**Stop** terminates the executing process group and leaves partial artifacts
available for diagnosis. An incomplete run never opens as a successful result.

## Native Linux and Windows WSL

On Linux, **auto** uses the native runtime. Choose the installed Foundation v10
`etc/bashrc`; `/opt/openfoam10/etc/bashrc` is discovered when available. An already
sourced environment also works with an empty bashrc field. VTK must be available
to the Python interpreter launching CleanroomX.

On Windows, **auto** selects WSL. Foundation v10 and a Python **3.11 or newer**
environment containing `vtk` must already be installed inside the selected WSL
distribution. Enter its Linux Python executable in **WSL Python 3.11+ (with vtk)**;
this can be a virtual environment's `bin/python`. The host GUI still needs the
application's `cfd` extras for analysis and graph display.

The launcher converts Windows paths using `wslpath`, exposes this exact installed
CleanroomX Python package to WSL through `PYTHONPATH`, sources the selected Linux
bashrc, and launches the solver CLI with individual arguments. A separate Linux
process group identifies the run; Stop signals that group before closing the
Windows client. No second CleanroomX checkout is required inside WSL.

The real solver verification was executed on Linux. Windows GUI/argument tests
exercise WSL command construction, path handling and group signaling contracts;
they do not substitute for a run on an actual Windows/WSL installation.

## What the calculations mean

The three cases are **isolated rectangular-room alternatives**, using current
room dimensions and declared or edited supply flow. They do not mesh placed
devices, obstacles, doors or inter-room connections. The model is steady,
isothermal and laminar. It does not solve turbulence, heat, contaminant or
particle transport. Those fields remain unavailable unless a separate real
solver result supplies them.

Field means are weighted by verified VTK cell volumes. Pressure `p` retains its
native kinematic units (`m²/s²`); a configured room pressure setpoint is not a
computed pressure field. Boundary balance reads signed native `phi` values.
Whole-domain supply ACH is `3600 × gross inlet phi / sum of VTK cell volumes`.
It is not outdoor-air ACH or an internal doorway-flow measurement.

The execution receipt binds synchronization manifests, solver/mesh logs, final
flux bytes and mesh boundary bytes. Reanalysis rejects changed bound evidence.
No project acceptance threshold is invented for flow imbalance. Process success,
import integrity and plotted residuals do not establish convergence, mesh
independence, physical cleanroom performance or certification.

## Verification

`scripts/verify_desktop_solver.py NEW_OUTPUT_DIRECTORY` drives the actual Tk room
Run button, executes Foundation v10, verifies original field files, checks all
three flux/ACH calculations, exports analysis and captures real desktop images.
The OpenFOAM CI workflow runs this check before its nine-case grid study and
uploads the complete run artifacts. Linux and Windows desktop jobs also execute
the integrated GUI and runtime command tests without allowing unexplained skips.
