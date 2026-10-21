# Live solver numerical preview — 21 October 2026

Baseline: clean branch `feat/doors-5pa-ceiling-downflow-demo-20261020`,
commit `8c7da24eb23a015b8c319f8b36f29387c4299c27`, synchronized with origin.
Existing PR: [#1363](https://github.com/3more102/CleanroomX-Cleanroom-Design-Simulation-Verification-Platform/pull/1363).

## Result

Fresh native and WSL run actions now select a separate **Live solver** panel.
It follows the actual growing `simpleFoam.log` without changing execution,
configured controls or source files. The panel shows the last observed SIMPLE
iteration, per-field initial/final linear residuals with their own iteration
identities, raw signed continuity diagnostics and the existing interactive
residual controls. Its small-window content scrolls in both directions.

The incremental parser/follower is in `cfd_live_monitor.py`; the dedicated
panel is in `cfd_live_monitor_gui.py`. Reads are bounded to 128 KiB per poll,
lines to 16 KiB, fields to 32 and the active chart history to 4,000 residual
entries, retaining whole iterations and original residual-entry indices.
Incomplete trailing lines stay pending. Detected replacement/truncation/removal
clears prior samples. Malformed/nonfinite records stop only the preview;
symbolic, nonregular and pre-existing fresh-run logs are rejected.

Preview offsets are independent of the raw-log text viewer. Final chunks
continue draining after worker completion, including when several stage
events arrive in one poll. Cancellation retains a labelled partial preview.
Import, a fresh case/run and case browsing clear preceding preview state.

The preview's explicit schema has no saved-field identity or convergence
verdict. Its chart draws no saved-field marker or convergence thresholds.
The canonical completed-run importer remains responsible for receipt, input,
log, mesh and field checks and for the existing numerical/engineering panels.
The previously implemented recorded-field controls retain their behavior.

## Executed checks

Python 3.12.14, Tcl/Tk 9.0.4, VTK 9.3.1, Matplotlib 3.10.8, pytest 9.1.1 and an
actual Tk/VTK display supplied by Xvfb.

| Check on final implementation | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Incremental parser, actual Tk monitor, cancellation, WSL routing and responsive residual controls | 51 | 0 | 0 |
| Complete suite on actual display | 2865 | 0 | 25 |

The focused checks overlap the complete suite. Complete execution took
**158.89 seconds**, exit 0, with 40 existing Matplotlib deprecation warnings.
The 25 capability skips are **24 actual Foundation v10 execution tests** and
**one optional native IFC test**. Neither dependency is installed in this
environment. The [original complete log](full-suite.log),
[focused log](focused-suite.log) and [source/evidence hashes](validation.json)
are retained. Workflow YAML parses and final capture image/implementation
hashes were independently rechecked.

Commands used an actual local display wrapper equivalent to Xvfb plus:

```bash
python -m pytest -q tests/test_cfd_live_monitor.py \
  tests/test_cfd_live_monitor_gui.py tests/test_cfd_residual_plot.py \
  tests/test_cfd_cancellation_gui.py tests/test_cfd_wsl_gui.py \
  tests/test_cfd_responsive_gui.py tests/test_cfd_responsive_v3.py -ra
python -m pytest -q -ra
```

The tests cover arbitrary byte boundaries, incomplete lines, repeated pressure
solves, exact zeros, signed continuity values, invalid records, bounded large
logs, stale/symbolic/nonregular logs, replacement/truncation/removal and final
log drainage. Actual Tk checks exercise a responsive controlled native worker,
cancellation, an independent WSL log offset, exact probes, clearing and wheel
scrolling at **850 × 600**, with zero callback errors. Controlled workers and
synthetic logs are software contracts, not successful CFD run evidence.

The new `test_actual_gui_run_streams_residuals_before_canonical_field_import`
generates and runs a fresh real case through the GUI, compares its preview
history with canonical field import, and verifies the preview cannot publish
fields. It requires actual Foundation v10 and was **skipped locally**. The
existing OpenFOAM execution workflow includes it; no current remote outcome is
claimed by this report. The display workflow also includes the new parser and
GUI tests.

## Recorded-data integration and capture

The parser replayed the original archived `simpleFoam.log`, split into small
chunks, and matched **all 400 residual entries** against the canonical parser.
The [actual running-widget capture](../../docs/live-solver-monitor-20261021/README.md)
uses the canonically verified original **13,210-cell**, iteration-**100** case.
It explicitly displays **RECORDED LOG REPLAY — no new solver execution**.
Its manifest records source/image/implementation hashes, zero callback errors,
no computed fields published by the preview, and no saved-field marker.

This original design-flow case did **not** report convergence. No new local
solver execution, convergence improvement, Windows-to-WSL platform validation,
closed-door leakage/5 Pa control, mesh independence or physical particle
qualification is established. **Engineering release remains HOLD.**
