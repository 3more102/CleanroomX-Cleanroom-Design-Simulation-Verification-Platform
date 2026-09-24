# Deployment

## Requirements

- Python 3.11, 3.12, or 3.13.
- Tk support for the desktop GUI.
- No third-party runtime Python dependencies are declared by the package.
- The development/test extra installs pytest.

## Install

For a normal local installation from the repository:

```bash
python -m pip install .
```

For development and validation:

```bash
python -m pip install -e .[dev]
python -m pytest -q
```

## Readiness checks

Validate the installed application registry without opening a window:

```bash
cleanroomx-gui --check
```

Launch the desktop application:

```bash
cleanroomx-gui
```

Open the self-contained demonstration bundled in the installed distribution:

```bash
cleanroomx-gui --demo
```

The wheel includes the demonstration project and all JSON dependencies required by its consistency and dossier analyses.

## Linux GUI smoke

The CI release path validates the real Tk application under Xvfb on Python 3.13. On Debian/Ubuntu-style systems the equivalent prerequisites are:

```bash
sudo apt-get update
sudo apt-get install -y xvfb tk
xvfb-run -a cleanroomx-gui examples/gui_demo.cleanroomx.json --smoke
```

## Production-use boundary

CleanroomX is an engineering screening/numerical tool. Deployment does not convert its outputs into cleanroom certification, CFD validation, commissioning/TAB acceptance, manufacturer approval, or regulatory compliance. Controlled organizations should apply their own document control, change control, verification, and approval procedures around the application.
