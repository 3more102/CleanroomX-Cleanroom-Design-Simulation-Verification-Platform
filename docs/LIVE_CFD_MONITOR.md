# Live solver log preview

The existing Multiroom CFD workspace has a **Live solver** panel. Starting a
fresh **Run OpenFOAM 10** or **Run case in WSL** operation selects this panel.
It shows the last observed SIMPLE iteration, per-field initial and final
linear residuals, raw continuity diagnostics and an interactive residual plot.
The latest-field table includes each entry's own iteration, so an incomplete
current iteration cannot make older field values appear current.

Use the field, initial/final, linear/log10 and recent-iteration controls, or
hover/click and use Left/Right to inspect exact entries. Repeated field solves
remain separate. Exact zero stays zero in probes; the log10 display retains
the existing explicitly documented display floor. SIMPLE iterations are not
physical seconds. The existing **Solver logs** tab remains available.
The live panel scrolls horizontally and vertically in smaller windows;
wheel scrolling over its chart moves the panel, while field controls keep
their normal interactions.

## Preview and verified results

The panel reads the actual `simpleFoam.log` as the worker writes it. These
bytes have not yet passed the completed-run receipt, log and field checks.
The preview deliberately has no saved-field marker, initial convergence
limits, convergence verdict or engineering verdict. Even a convergence
message in a partial log cannot publish a computed-field report.

After execution, enter the actual air density and reference room and select
**Import computed fields**. The original canonical importer checks retained
inputs, manifest, execution receipt, logs, mesh and fields before populating
the existing result panels. Import, browsing a different case and starting a
new run clear the preceding preview. Native cancellation retains a clearly
labelled partial preview; partial results still cannot pass import.

The Windows-to-WSL controls use the same preview reader on the shared case
directory. This does not add Windows-to-WSL cancellation or establish actual
Windows workstation qualification.

## Bounded incremental reading

- Each preview poll reads at most 128 KiB; it uses a separate offset from
  the raw text-log viewer, so stage changes cannot skip preview bytes.
- Incomplete trailing lines stay pending. Nonfinite/negative residuals,
  decreasing iteration labels and malformed diagnostic records stop the
  preview without interrupting the solver or bypassing import checks.
- At most 4,000 residual entries are retained, dropping whole older
  iterations. Total observed counts and original residual-entry indices
  remain available; the original log is untouched.
- Individual lines and field inventories are bounded. Symbolic logs and
  logs already present before a fresh run are rejected by the preview.
- Detected file replacement, removal or truncation clears earlier preview
  samples. This is a convenience reader, not a concurrent-file integrity
  audit; completed-result checks remain authoritative.
- Final unread chunks continue draining after worker completion. Neither
  process success nor a small final linear residual establishes convergence.

## Reproduction

```bash
python -m pytest -q tests/test_cfd_live_monitor.py
xvfb-run -a python -m pytest -q tests/test_cfd_live_monitor_gui.py
bash scripts/with_openfoam10.sh xvfb-run -a python -m pytest -q \
  tests/test_cfd_multizone_execution.py -ra
```

The last suite includes a fresh actual GUI-to-OpenFOAM run, preview-to-import
comparison and the existing lifecycle/field checks. It requires real
Foundation v10 and a display; skipping it is not solver execution evidence.

The [actual widget capture](live-solver-monitor-20261021/README.md) explicitly
replays an archived, unconverged log. It is not a new solver run. Numerical
convergence, closed-door leakage/5 Pa control, mesh independence and physical
particle qualification remain separate work. **Engineering release: HOLD.**
