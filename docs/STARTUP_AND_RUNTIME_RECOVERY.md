# Desktop startup and OpenFOAM environment recovery

This is a recovery increment on the existing project and PR #1363. It does
not replace the design model, CFD importer, native VTK viewer or particle model.

## Start the desktop on Windows

From the source checkout, double-click `start-cleanroomx.cmd`, or run:

```powershell
.\start-cleanroomx.ps1 --demo
```

The launchers select the checkout's `.venv` when present, otherwise the Windows
Python launcher or `python`. They locate `src` from their own directory. Python
3.11+ with Tcl/Tk is required. A sourced OpenFOAM environment and existing CFD
results are optional for the design workspace.

If startup fails, retain the full traceback from:

```text
%LOCALAPPDATA%\CleanroomX\Logs\cleanroomx-gui.log
```

`CLEANROOMX_LOG_DIR` overrides that location. An unwritable log folder retains
the original traceback on stderr. A no-argument failed CMD launch keeps the
console open so the error can be read; automated callers can set
`CLEANROOMX_NO_PAUSE=1`. Explicit command-line arguments never trigger this pause.

```powershell
.\start-cleanroomx.ps1 --check
.\start-cleanroomx.ps1 --demo --smoke --autosave-interval-seconds 0
```

`--check` validates application imports/registry without opening a window.
`--smoke` opens actual Tk widgets, renders the bundled 2D/3D layout and checks
its active analytical workflow. Neither is a CFD solver test. Unexpected Tk
idle/callback failures now produce a failing smoke exit code, rather than a
false PASS. Nonfinite autosave intervals are rejected before Tk starts.

## Discover OpenFOAM inside Linux or WSL

```bash
python3 -m cleanroomx.openfoam_runtime --json
# Installed console equivalent:
cleanroomx-openfoam-runtime --json
```

The inventory inspects `/opt`, `/usr/lib/openfoam`, `/usr/share/openfoam`,
`/usr/share`, `/usr/local`, the active `WM_PROJECT_DIR` and `~/OpenFOAM`, one
level deep with an inspection limit. It reports other detected version hints
without sourcing their startup scripts. A directory name is never proof of
compatibility: the inventory always says `runtime_verified: false`.

The current case dictionaries target **OpenFOAM Foundation v10 / simpleFoam**.
`scripts/with_openfoam10.sh` selects an eligible environment, checks all four
required utilities and interrogates the actual `simpleFoam -help` identity
before running the requested command. Other releases require explicit case
compatibility work and real solver tests; discovery does not add that support.

```bash
bash scripts/with_openfoam10.sh python3 -m cleanroomx.cfd_pipeline_cli --help
```

For a nonstandard installation, configure its absolute Linux path explicitly:

```bash
export CLEANROOMX_OPENFOAM_BASHRC='/mnt/d/OpenFOAM/OpenFOAM-10/etc/bashrc'
bash scripts/with_openfoam10.sh simpleFoam -help
```

An invalid explicit override fails with remediation; it does not silently pick
another installation. Runtime discovery does not move, install or modify any
OpenFOAM distribution, and does not recursively search a Windows drive.

## Configure Windows to WSL in the actual CFD window

In the existing Multiroom CFD window:

1. Select the installed WSL distribution.
2. Verify **WSL source checkout**. An installed wheel must select a source
   checkout containing the execution scripts; `site-packages` is not a checkout.
3. Leave **WSL OpenFOAM etc/bashrc** blank for discovery, or enter an absolute
   Linux path such as `/mnt/d/OpenFOAM/OpenFOAM-10/etc/bashrc`.
4. Click **Probe WSL** and inspect **Solver logs** for actual runtime diagnostics.
5. Generate a fresh connected case from a saved project before running it.

The same selection is available from PowerShell:

```powershell
.\run-cleanroomx-cfd-wsl.ps1 -Mode Probe -Distribution Ubuntu-22.04 `
  -OpenFOAMBashrc '/mnt/d/OpenFOAM/OpenFOAM-10/etc/bashrc'
```

These paths are examples, not claims about a workstation's installed files.
The path is passed as a separate argument, including spaces or shell metacharacters.
Probe failure details and the tail of actual WSL output reach the GUI through
its event queue. Four successful process stages and a verified receipt are
still required before computed fields can be imported.

## Installation guidance and limitations

- [OpenFOAM Foundation v10 Ubuntu installation](https://openfoam.org/download/10-ubuntu/)
  explicitly lists its packaged Ubuntu versions; use that list rather than
  assuming the package supports an arbitrary newer Ubuntu release.
- [OpenFOAM Foundation Windows/WSL guide](https://openfoam.org/download/windows/)
  describes the WSL setup; [Microsoft WSL commands](https://learn.microsoft.com/en-us/windows/wsl/basic-commands)
  describes listing and selecting installed distributions.
- A missing `0/U` is a missing original solver input. Recreate a complete case;
  do not invent a replacement field or bypass its input hash to accept a results-only folder.
- Linux execution does not verify the native Windows-to-WSL bridge. The CI
  workflow now requests real Windows Tk startup from an unrelated directory,
  as well as Bash/display regression tests. Inspect the per-commit CI outcome.
- A solver finishing is distinct from convergence, mesh independence, physical
  accuracy or cleanroom qualification. Engineering release remains **HOLD**.

See the [executed milestone report](../reports/startup-runtime-recovery-20261021/REPORT.md)
for commands, measured counts, source integrity evidence and remaining work.
