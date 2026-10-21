# Responsive multiroom CFD workstation (v3)

The Multiroom CFD Tk window now fits the available screen using the shared
`fit_window_to_display` utility. Run/import/cancel/export actions occupy
their own row. Windows-to-WSL controls start collapsed, can be shown with
**Show WSL settings**, and are not shown on Linux.

The **Room comparison**, **Iteration stability**, and **Closed-door network**
tabs now scroll vertically and horizontally. Read-only chart canvases and
labels route mouse-wheel movement to their tab; Treeview, Text, scrollbar
and custom zoom controls retain their own native bindings. A compact
**Jump to panel** selector provides access to all notebook tabs.

## Tests
```bash
xvfb-run -a python -m pytest -q \
  tests/test_cfd_responsive_gui.py \
  tests/test_cfd_responsive_v3.py \
  tests/test_cfd_wsl_gui.py \
  tests/test_gui_windowing.py
```

This is a desktop-layout change, not a CFD or cleanroom-acceptance change.
Room pressures, real solver provenance, numerical criteria, mass balances,
particle screening, and engineering HOLD remain unchanged. The prior 18
local patch/installer tests passed separately; the full repository test
suite and Foundation v10 solver qualification are not claimed as run by
this GitHub-only change.
