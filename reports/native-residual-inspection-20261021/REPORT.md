# Native residual inspection increment — 21 October 2026

Starting branch: `feat/doors-5pa-ceiling-downflow-demo-20261020`.
Starting commit: `6b97fc5b5bdc189e23912c42bc41d3991f9a9fde`.
Existing PR: [#1363](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/pull/1363).

## Result

The existing desktop residual panel now supports field selection, initial vs
final linear residuals, linear/log10 scales, recent recorded-iteration windows,
and exact mouse/keyboard entry inspection. The chart retains actual SIMPLE
iteration coordinates, repeated field solves and log order. Initial limits
are shown only for initial residuals. Views preserve the imported report and
its solver/engineering verdicts. The native controls are separate from the
existing offline HTML dashboard, whose per-field log index has a different
meaning from a recorded SIMPLE iteration.

The implementation is in `src/cleanroomx/cfd_residual_plot.py`, connected by
`cfd_multizone_gui.py`. Dedicated regression tests and the existing CFD VTK
display workflow cover the new widget. The recorded initial/final CSV export
remains available through the existing Export report action.

## Executed verification

Python 3.12.14, Tcl/Tk 9.0.4, VTK 9.3.1, pytest 9.1.1, native Tk on Xvfb.

| Check | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Focused new plot + responsive workspace suite on an actual display | 21 | 0 | 0 |
| Complete suite on an actual display | 2843 | 0 | 24 |

The focused count overlaps the full suite. Full execution took 162.22 seconds,
exit 0; the original [log](full-suite.log) and its [SHA-256](log-sha256.json)
are retained. The 24 skips comprise 23 actual Foundation v10 execution tests
and one optional native IFC test. No running OpenFOAM runtime or IFC dependency
was installed in this environment. Forty existing Matplotlib positional-font
deprecation warnings were emitted. The complete suite did execute the native
Tk/VTK viewer tests, the new plot tests and existing responsive GUI tests.

Commands used a local display wrapper equivalent to starting Xvfb and running:

```bash
python -m pytest -q tests/test_cfd_residual_plot.py \
  tests/test_cfd_responsive_gui.py tests/test_cfd_responsive_v3.py -ra
python -m pytest -q -ra
```

An initial [headless complete attempt](headless-attempt.log) recorded 2727 passed,
139 skipped and one failure: the existing native VTK GUI test called `tk.Tk()`
without a display. Its original traceback is retained. Providing the actual
display resolved that environmental failure without changing or suppressing
the existing test. Early display setup also required the X keyboard compiler
and its library; the final passing run used the functioning display server.

## Recorded-data GUI evidence

The [three actual captures](../../docs/native-residual-inspection-20261021/README.md)
use the original archived 13,210-cell, 100-iteration design-flow case. The
canonical importer verified its input/receipt/log/mesh/output hashes, and
reimported the report after capture. The manifest records implementation and
image hashes, exact active controls and inspected values, and zero callback
errors. `scripts/capture_residual_inspection_gui.py` reproduces these captures
on a real display. All screenshot and implementation hashes were rechecked.

No new solver run or convergence improvement is claimed. The original run is
unconverged; the capture still shows NOT CONVERGED and engineering HOLD.
Synthetic tests separately cover repeated solves, gaps, zeros, invalid data,
offscreen saved-field markers, filters, mouse/keyboard probes and clearing.

Closed-door leakage/control, mesh independence, physical contamination and
particle qualification remain outstanding. **Engineering release stays HOLD.**
