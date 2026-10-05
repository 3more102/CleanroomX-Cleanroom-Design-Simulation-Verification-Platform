# Windows standalone distribution

CleanroomX CI builds a self-contained Windows x64 workstation artifact in the
`Windows Standalone` workflow.

The artifact contains a PyInstaller one-directory build of the production
`cleanroomx.gui:main` entry path together with the optional BIM dependency.
The build gate launches the frozen `CleanroomX.exe --check` process on a clean
GitHub-hosted Windows runner before the artifact is published.

## Release artifact

The workflow publishes:

- `CleanroomX-windows-x64.zip`
- `CleanroomX-windows-x64.sha256`

Verify the SHA-256 sidecar before distributing the archive. After extraction,
launch `CleanroomX.exe` from the `CleanroomX` directory. A separate Python
installation is not required by the frozen artifact.

The build intentionally uses an onedir layout rather than a one-file
self-extractor. This keeps bundled native libraries explicit and avoids
extracting executable engineering software into a transient directory on every
launch.

## Build reproduction

On Windows with Python 3.12:

```powershell
python -m pip install --upgrade pip
pip install -e ".[bim]"
pip install "pyinstaller==6.22.3"
.\scripts\build_windows_standalone.ps1
```

The PyInstaller version is pinned in CI. The repository source revision and the
workflow run identify the remaining build inputs.

## Current boundary

This artifact is a portable standalone distribution, not yet a registered
Windows installer. It does not currently create Start Menu shortcuts, register
an uninstaller, or perform in-place upgrades. Those installer lifecycle gates
must be completed before claiming the Windows installation/uninstallation
release gate is fully passed.
