# Design Studio reference-parity audit

Audit date: 2026-10-19  
Implementation base: `feat/real-design-studio-20261018` at `3ef520b37066f9a3725d4d56d0204e1160ad86ca`.

## Evidence standard

The reference is a **visual and interaction target**, not a substitute for
measured behavior. A source-code inspection cannot establish screenshot parity,
solver integration, or zero regression failures. Treat every category below as
**not yet accepted** until its enumerated checks pass on the same revision.

The implementation currently uses Tkinter and the canonical spatial model.
It deliberately renders an architectural 3D cutaway, not genuine alpha-blended
3D surfaces. See `docs/DESIGN_STUDIO_IMPLEMENTATION.md`.

## Acceptance matrix and denominators

| Category | Acceptance denominator | Verification required | Status |
| --- | ---: | --- | --- |
| Visual reference parity | 12 visual elements: header, workflows, toolbar, palette, metric cards, 3D scene, room proportions, labels, navigator, inspector, camera controls, responsive layout | Side-by-side genuine 1920×1080 screenshots, reviewed against the reference | Not measured |
| Functional GUI | 10 behaviors: open/demo, edit room, edit device, undo/redo, select, focus, isolate, views, save/reload, validate | Real Tk interaction tests | Partially covered; no complete run recorded here |
| 3D interactions | 7 behaviors: orbit, pan, zoom, focus, isolate, view preset, fitting | Real canvas interaction tests | Not fully verified |
| Room/device synchronization | 6 behaviors: live cards, move navigator, resize navigator, bidirectional room selection, inspector, device counts | Tests plus save/reload | Relocation and aspect-ratio regressions added; CI pending |
| OpenFOAM integration | Explicit capability matrix for case generation, mesh, boundary conditions, execution, log parsing, field import, GUI plots | Actual Foundation v10 case execution and provenance audit | Not verified by this GUI-only change |
| Automated verification | Focused Tk tests, spatial GUI regressions, full Python regression, Windows smoke | Saved CI results and failure/skip counts | Pending CI results |

Completion percentage is **verified accepted checks / specified denominator ×
100**, but only after each check has objective evidence. No percentage is
reported before that evidence exists.

## 2026-10-19 code corrections

- The Room Navigator now considers room X/Y position, length and width in its
  refresh signature, rather than only ID/name/floor area. Moving a room, or
  changing its aspect ratio without changing area, refreshes the miniature map.
- The room panel now labels the project value as **Configured pressure**; it
  does not imply that OpenFOAM solved the pressure field.
- Regression tests cover both cases using the real Tk navigator, and confirm
  the pressure label for the bundled demonstration.
- The real-Tk capture helper accepts an explicit width and height and rejects
  output whose actual window size differs from the requested size.
- Design Studio preview CI requests both 1536×960 reference-scale and
  1920×1080 captures, using a large enough Xvfb display. These files become
  evidence only after the corresponding workflow completes successfully.

## Reproduction commands

From a checkout of the change branch, with the project installed:

```powershell
python -m pytest -q tests/test_gui_design_studio.py tests/test_spatial_editing_gui.py
python -m pytest -q
cleanroomx-gui --demo
python tools/capture_design_studio_ci.py --width 1920 --height 1080 --output studio-1080p.png
```

Do not treat a headless-only test as a GUI acceptance test: the real Tk tests
require a display (Windows desktop or Xvfb). For screenshot evidence, use the
repository's real-GUI capture script in `tools/capture_design_studio_ci.py`.

## Outstanding evidence

- Obtain and review both **1920×1080** and reference-scale CI screenshots;
  independently verify the Windows GUI layout against the reference.
- Verify all stage controls, room/device editing and persistence end-to-end.
- Verify supported OpenFOAM capabilities against real solver output; separate
  configured/analytical, computed, sample and unsupported results.
- Review full regression counts and address critical/high-severity failures.

No screenshot, solver result, verified percentage or successful test run is
claimed by this audit document.
