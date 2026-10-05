# Deployment

## Requirements

- Python 3.11, 3.12, or 3.13.
- Tk support for the desktop GUI.
- No third-party runtime Python dependencies are declared by the package.
- The development/test extra installs pytest.

## Install

Normal local installation from the repository:

```bash
python -m pip install .
```

Development and validation:

```bash
python -m pip install -e .[dev]
python -m pytest -q
```

## Readiness checks

Validate package version plus the complete desktop application registry without opening a window:

```bash
cleanroomx-gui --check
```

Launch the desktop application:

```bash
cleanroomx-gui
```

Open the bundled demonstration project:

```bash
cleanroomx-gui --demo
```

## Linux GUI smoke

The CI release path validates the real Tk application under Xvfb on Python 3.13. On Debian/Ubuntu-style systems:

```bash
sudo apt-get update
sudo apt-get install -y xvfb tk
xvfb-run -a cleanroomx-gui examples/gui_demo.cleanroomx.json --smoke
xvfb-run -a python -m pytest -q tests/test_spatial_editing_gui.py
```

The second command exercises room duplication, attached-device movement,
property validation, project undo/redo, persistence, analysis execution, and
toolbar visibility through real Tk widgets. It requires a source checkout and
the development/test extra. Headless test runs skip these GUI cases; CI runs
them explicitly under Xvfb and treats an unusable configured display as an error.

## Production-use boundary

Deployment does not convert CleanroomX screening/numerical outputs into cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance. Controlled organizations should apply their own document control, change control, verification, and approval procedures.


## Installed-wheel release verification

The Release 2/v0.101 CI release gate builds a wheel on Python 3.11, 3.12, and 3.13, installs it into a clean virtual environment, runs `cleanroomx-gui --check`, verifies packaged demo resources, and on Python 3.13 launches the installed `cleanroomx-gui --demo --smoke` under Xvfb.


## Standalone Windows installer release gate

The release CI builds a 64-bit Windows desktop distribution with PyInstaller and
packages it with Inno Setup. The installer is per-user by default, creates
Start-menu integration, exposes an optional desktop shortcut, carries explicit
Windows product/file metadata and a CleanroomX application icon, and includes an
uninstaller.

The required Windows release job validates the complete artifact on a fresh hosted runner:
standalone launch, a silent baseline install, an in-place upgrade to the current
installer using the stable application identity, installed `--check`, installed GUI
`--demo --smoke`, and silent uninstall. It also publishes a
SHA-256 manifest recording the exact Git commit, CleanroomX version, PyInstaller
version, IfcOpenShell version, and runner image used for the build.

Build from a Windows checkout with Python 3.12 by running:

```powershell
.\packaging\windows\build_installer.ps1
```

The release extra pins PyInstaller and the IFC runtime used in the standalone
artifact; the required CI job installs and verifies Inno Setup 7.1.0 exactly. Code signing is intentionally not performed by repository CI because a
trusted signing certificate/private key is an external release credential.
