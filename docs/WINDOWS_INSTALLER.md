# Windows standalone installer

CleanroomX has a Windows x64 standalone packaging gate in
`.github/workflows/windows-installer.yml`.

The gate is separate from the Python wheel path. It builds the desktop application
with an embedded Python runtime, packages it as a per-user Windows installer, and
then exercises the installer lifecycle on a clean GitHub-hosted Windows runner.

## Pinned packaging stack

The workflow currently pins:

- PyInstaller 6.22.3;
- IfcOpenShell 0.9.0, so the standalone build retains native IFC support;
- Inno Setup 7.1.0;
- immutable SHA references for GitHub Actions.

Changing any packaging-tool version is a release-engineering change and must pass
the complete installer lifecycle again.

## Build shape

The PyInstaller build is a one-folder x64 desktop application named
`CleanroomX.exe`. It collects the complete `cleanroomx` package, packaged demo
resources, and IfcOpenShell modules/data.

The Inno Setup package uses a stable application identity and installs by default
under:

`%LOCALAPPDATA%\Programs\CleanroomX`

This avoids requiring administrator privileges for the standard workstation
installation path.

## Release gate

The Windows installer workflow must pass all of the following:

1. import the pinned IfcOpenShell runtime;
2. build the standalone application;
3. run standalone `CleanroomX.exe --check`;
4. run the real standalone GUI demo smoke;
5. build a baseline installer and the current installer with the same stable AppId;
6. perform a silent clean install;
7. perform an in-place version upgrade over that installation;
8. run installed `--check` and GUI demo smoke;
9. execute the generated uninstaller;
10. verify the primary executable is removed;
11. upload only the installer that passed the lifecycle gate.

The baseline installer uses the current application payload with an older installer
version solely to exercise deterministic Inno Setup upgrade semantics. It is not a
substitute for project-schema migration tests, which remain covered by the project
persistence suite.

## Local build prerequisites

The CI workflow is the canonical reproducible build recipe. A manual Windows build
requires Python 3.12, the pinned PyInstaller and IfcOpenShell versions, and Inno
Setup 7.1.0.

The generated CI installer is an unsigned validation artifact. If CleanroomX is
distributed publicly, Authenticode signing and organization-specific publisher
identity should be applied in a controlled release workflow without exposing the
private signing key to pull-request builds.
