# Design Studio reference parity — evidence ledger

Reference target: original CleanroomX Design Studio screenshot, dark navy/cyan
UI, three-room Process / Preparation / Ante–Airlock demonstration.
Branch: `chatgpt/design-studio-reference-parity-20261019`
Base: `main` at `cf5506ffc5793313e023118209faafefc17e73b7`.

## Verified source audit

- Desktop entry point: `cleanroomx-gui --demo` in `pyproject.toml`.
- Framework: Tkinter / ttk. 2D and projected 3D rendered through Tk Canvas.
- Core workspace: `src/cleanroomx/spatial.py:SpatialDesignWorkspace`.
- Canonical model: project `spatial_layout` with `rooms`, `devices`,
  and view settings; `layout_metrics` supplies geometric totals.
- Existing controls include room/device editing, 2D/3D/Split, camera presets,
  fit/isolate, inspector properties, save/history and engineering overlays.
- Bundled demo room dimensions yield 3 rooms / 62 m² / 186 m³. These values
  are **not** hardcoded in the new UI.

## Increment implemented in this branch

- [x] Four cards showing model-derived room count, floor area, geometric
  volume and all placed devices/openings.
- [x] Mini 2D floor-plan navigator with clickable selection and a room table
  including live floor area, synchronized to the existing shared selection.
- [x] Selected-room panel showing class, dimensions, area, volume, device
  count and clearly **configured** (not CFD-computed) pressure.
- [x] Categorized device totals for selected room or whole layout.
- [x] Focus Room, Isolate Room, Restore All Rooms and Studio View buttons
  reusing real workspace operations.
- [x] Additional GUI acceptance tests submitted to repository.

## Outstanding requirements / limitations

- [ ] Actual Windows GUI launch on target computer and genuine baseline
  and after screenshots at 1920×1080. Not available in GitHub-only work.
- [ ] Visually compare screenshots against the user's original reference.
- [ ] Validate geometry proportions, responsive layout and design theme.
  This increment uses the existing ttk theme, not a complete visual restyle.
- [ ] Investigate the inspector vertical scrolling in smaller windows.
- [ ] Test all GUI controls manually on Windows.
- [ ] Verify OpenFOAM v10 solver and CFD field provenance end to end.
- [ ] Complete full project regression and user acceptance.

## Completion policy

Never report a percentage without a fixed denominator and verified evidence.
The six reporting categories are:
1. Visual reference parity: passed visual acceptance items / all defined
   screenshot acceptance items; requires real screenshot evidence.
2. GUI completeness: passed interactive GUI acceptance cases / registered cases.
3. 3D interaction coverage: passed click/orbit/pan/zoom/section/focus/isolation
   cases / registered 3D cases.
4. Room/device synchronization: passed model-to-viewport, navigator, inspector,
   persist/reload cases / registered synchronization cases.
5. OpenFOAM integration: verified solver execution + validated output field
   transfer cases / documented v10 integration test matrix.
6. Automated verification: passed configured test cases / all executed and
   applicable configured cases, with failure/skip/error counts separately.

At writing, the complete denominators and environment-based checks have
**not been established**. All aggregate percentages are **NOT MEASURED**,
not zero and not 100%.

## Reproduction

```powershell
cd C:\Users\omar\CleanroomX-Cleanroom-Design-Simulation-Verification-Platform
git fetch origin
git switch chatgpt/design-studio-reference-parity-20261019
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_gui_design_studio.py tests/test_spatial_editing_gui.py
cleanroomx-gui --demo
```

In headless Linux, use
`xvfb-run -a python -m pytest -q tests/test_gui_design_studio.py`.

No native target screenshot, test execution or OpenFOAM execution is claimed
solely because a file or test has been committed.
