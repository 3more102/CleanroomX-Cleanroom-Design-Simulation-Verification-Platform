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

Launch the desktop application from a terminal:

```bash
cleanroomx-gui
```

On Windows, an installed package also provides `cleanroomx-desktop`, a
`gui_scripts` launcher that starts the same desktop application without
creating a console window. Keep `cleanroomx-gui` for command-line automation
such as `--check` and `--smoke`, where console process semantics and output
are useful.

Open the bundled demonstration project from a terminal:

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

The current CI release gate builds a wheel on Python 3.11, 3.12, and 3.13, installs it into a clean virtual environment, runs `cleanroomx-gui --check`, verifies packaged demo resources, and on Python 3.13 launches the installed `cleanroomx-gui --demo --smoke` under Xvfb. The Windows job also verifies that `cleanroomx-desktop` is installed through the `gui_scripts` group and that its `--check` path exits successfully.
