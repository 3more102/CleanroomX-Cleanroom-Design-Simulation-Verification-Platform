# Windows-to-WSL execution of a connected CleanroomX CFD case

This is an **opt-in execution bridge**, not an installer or replacement for
the native GUI solver button. The Windows GUI generates input and later imports
recorded results; OpenFOAM Foundation v10 executes inside Linux/WSL.

## Requirements and preflight

- Windows 11 and a working WSL Linux distribution named Ubuntu (or another
  explicitly selected installed distribution).
- Windows Python 3.11+ and a CleanroomX checkout containing this bridge.
- Linux Python 3 and required CleanroomX dependencies inside WSL.
- **OpenFOAM Foundation v10** installed inside the selected WSL distribution,
  with a readable /opt/openfoam10/etc/bashrc, blockMesh, checkMesh,
  simpleFoam, and postProcess.

In **Windows PowerShell**, from the repository root:

```powershell
wsl --list --verbose
.\run-cleanroomx-cfd-wsl.ps1 -Mode Probe -Distribution Ubuntu
```

The probe invokes the existing verified Linux Foundation v10 wrapper, checks
the runtime and imports the CleanroomX Python CLI. It does not execute a
CFD case. If the bashrc file is absent, WSL does not have the required
OpenFOAM version. Follow the [official v10 installation documentation](https://openfoam.org/download/10-ubuntu/)
for a supported Linux distribution. Do not assume that Ubuntu 26.04 offers
a compatible v10 package. The bridge never installs or substitutes a solver.

## Generate, execute and inspect

Create a **new, previously nonexistent** connected **open-door** case using
the GUI Analyze > Generate Connected Open-Door CFD Case command, or the existing
CleanroomX CLI on Windows:

```powershell
python -m cleanroomx.cfd_pipeline_cli multizone-generate .\examples\gui_demo.cleanroomx.json .\open-door-case --door-mode open --kinematic-viscosity-m2-s 1.5e-5 --max-iterations 600 --output-interval 50
```

These air-property and solver settings are illustrative design assumptions,
not measurements of an actual facility. Once the WSL probe succeeds, execute
**that same case** in Windows PowerShell:

```powershell
.\run-cleanroomx-cfd-wsl.ps1 -Mode Run -CaseDirectory (Join-Path (Get-Location) "open-door-case") -Distribution Ubuntu -TimeoutSeconds 3600
```

The bridge converts both Windows paths using the selected distribution's
wslpath utility and passes paths as separate Bash arguments (without shell
source interpolation). It invokes the existing verified Foundation v10 wrapper
to run the existing multizone-run CLI. Input manifest checks, stage logs,
return codes and output receipts still belong to the existing CFD runner.

The Windows case directory retains real OpenFOAM output, logs and
run-receipt.json. Back in the desktop GUI, open Run / Review Multiroom CFD
and **Import recorded fields** using an explicit actual air density and
modeled reference room ID; review selected iteration, residuals, pressure,
velocity, room balances and engineering HOLD reasons. The GUI's own Run
button still requires locally available OpenFOAM; use this launcher for WSL.

## Failure behavior, evidence and limits

- Absent inputs, missing WSL mounting, missing v10 environment, unsupported
  solver identity, absent Linux Python dependencies and failed solver stages
  are errors, not successful computational results.
- Nonzero WSL process status propagates to the Windows PowerShell caller.
- Failed stages may leave incomplete logs and receipts. Generate a fresh case;
  do not overwrite those files.
- Contract tests check argument isolation, path verification and error
  propagation. **Actual Windows/WSL execution has not yet been verified on
  the user's machine.** The bridge cannot execute a WSL-only case path not
  available to the Windows host.
- Successful execution alone establishes neither numerical convergence nor
  the specified closed-door 5 Pa pressure cascade. Cleanroom performance,
  particle deposition and regulatory compliance remain unverified.
  Engineering release remains **HOLD**.

Unit contract tests (these are not solver-execution evidence):

```bash
python -m pytest -q tests/test_cfd_wsl_bridge.py
```
