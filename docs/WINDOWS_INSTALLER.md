# Windows registered installer

CleanroomX release validation includes a registered per-user Windows x64 installer
built from the already-smoke-tested self-contained workstation distribution.

The installer is an Inno Setup package with a stable application identity. It
installs under the current user's local application data, creates a Start Menu
entry, registers an uninstaller, and does not require a separate Python
installation. The installer and installed workstation use the repository-owned
CleanroomX application icon, and installer version metadata is populated from
the same project version passed to the registered package.

## Release gate

The `Windows Installer Lifecycle` workflow uses a fresh `windows-2025`
GitHub-hosted runner and performs the complete lifecycle:

1. build the self-contained PyInstaller workstation;
2. validate the frozen executable's icon/version-resource build inputs and
   Windows product metadata;
3. compile a registered, branded installer;
4. install a baseline package silently;
5. execute installed `CleanroomX.exe --check`;
6. install the current package over the baseline installation;
7. verify the registered `DisplayVersion` changed to the current project
   version;
8. execute the upgraded `CleanroomX.exe --check`;
9. run the registered uninstaller;
10. verify the executable and uninstall registration are removed.

This gate validates application installation mechanics and startup readiness. It
does not replace engineering regression tests, native IFC validation, or the
full Tk suite.

## Artifact

The workflow publishes the versioned installer executable and a SHA-256 sidecar
from `dist/windows-installer`.

The package is intentionally per-user (`PrivilegesRequired=lowest`) so normal
desktop installation and automated clean-runner validation do not require
machine-wide administrative state.

## Reproducing the build

First produce the self-contained distribution, then compile the installer:

```powershell
python -m pip install -e ".[bim]"
python -m pip install "pyinstaller==6.22.3"
.\scripts\build_windows_standalone.ps1
.\scripts\build_windows_installer.ps1 -SkipStandaloneBuild
```

Run the complete install/upgrade/uninstall check with:

```powershell
.\scripts\test_windows_installer_lifecycle.ps1
```

The `release` extra pins the frozen-build Python dependencies to the same
versions used by CI. The build script reads the release version from
`pyproject.toml`. The Inno
Setup application identifier is stable across builds so an installer of a later
CleanroomX version upgrades the same registered product rather than creating a
parallel installation.

## Current boundary

The installer is not code-signed in this repository. Organizations distributing
CleanroomX outside controlled environments should sign the installer and frozen
executables with an organization-controlled Authenticode certificate and apply
their own release approval process.
